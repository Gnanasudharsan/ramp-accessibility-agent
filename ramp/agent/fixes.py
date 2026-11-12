"""Fix generation (source patches) and verification (re-render, re-check, compare).

A fix is a single exact-substring replacement in one source file. That constraint keeps diffs
minimal, makes them trivially reviewable, and lets verification apply each fix in isolation.

Verification (``verify_fix``) copies the site to a temp dir, applies the patch, serves it, and
counts the fix as a success only if all three hold:
1. the targeted violation is gone (same rule no longer fires on that element; for judgment-based
   findings the same check is re-run on the patched element),
2. no new violations appear (per-rule axe counts never increase), and
3. the page still renders (HTTP 200, no script errors, text still present), with a pixel-diff
   ratio recorded as a visual-diff signal.
"""

from __future__ import annotations

import difflib
import io
import shutil
import tempfile
from collections import Counter
from collections.abc import Awaitable, Callable
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image, ImageChops
from playwright.async_api import Browser
from pydantic import BaseModel, Field

from ramp.agent import prompts
from ramp.checks.axe import run_axe, violations_to_issues
from ramp.checks.source_map import SourceCandidate, map_to_source
from ramp.crawler.crawler import new_readonly_context
from ramp.crawler.urls import origin_of
from ramp.evals.static_server import StaticServer
from ramp.models.llm import LLMError, StructuredLLM, raw_block, untrusted_block
from ramp.report.schema import Issue

MIN_SOURCE_SCORE = 4.0  # tag match plus at least one distinctive attribute
MAX_CHANGED_LINES = 15
CONTEXT_LINES = (12, 18)


class FixProposalLLM(BaseModel):
    old: str = Field(min_length=1, max_length=4000)
    new: str = Field(max_length=4000)
    explanation: str = Field(max_length=600)


class ProposedFix(BaseModel):
    id: str
    issue_id: str
    file: str  # relative to repo root
    line: int
    old: str
    new: str
    explanation: str
    diff: str
    attempt: int = 1
    status: str = "proposed"  # proposed | verified | failed | needs_human
    failure: str | None = None
    violation_gone: bool = False
    no_new_violations: bool = False
    renders: bool = False
    visual_diff_ratio: float | None = None


class NeedsHuman(BaseModel):
    issue_id: str
    reason: str


def served_file(page_url: str, repo: Path) -> str | None:
    """The repo file served at ``page_url`` when the repo is a static site root."""
    path = urlsplit(page_url).path.lstrip("/") or "index.html"
    if path.endswith("/"):
        path += "index.html"
    return path if (repo / path).is_file() else None


def locate_source(issue: Issue, repo: Path) -> SourceCandidate | None:
    candidates = map_to_source(
        issue.evidence.html_snippet, repo, top_k=1, prefer_file=served_file(issue.page_url, repo)
    )
    if not candidates or candidates[0].score < MIN_SOURCE_SCORE:
        return None
    return candidates[0]


def unified_diff(path: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            n=2,
        )
    )


def validate_patch(source: str, old: str, new: str) -> str | None:
    """Return a reason the patch is unacceptable, or None."""
    if old == new:
        return "replacement is identical to the original"
    count = source.count(old)
    if count == 0:
        return "`old` is not an exact substring of the file"
    if count > 1:
        return f"`old` occurs {count} times; it must be unique"
    if "<script" in new.lower() and "<script" not in old.lower():
        return "fix must not add scripts"
    changed = sum(
        1 for line in difflib.ndiff(old.splitlines(), new.splitlines()) if line[:1] in "+-"
    )
    if changed > MAX_CHANGED_LINES * 2:
        return f"diff too large ({changed} changed lines)"
    return None


async def propose_fix(
    llm: StructuredLLM, issue: Issue, repo: Path, feedback: str | None = None, attempt: int = 1
) -> ProposedFix | NeedsHuman:
    located = locate_source(issue, repo)
    if located is None:
        return NeedsHuman(issue_id=issue.id, reason="could not locate the source of this element")
    source = (repo / located.path).read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    start = max(0, located.line - 1 - CONTEXT_LINES[0])
    excerpt = "".join(lines[start : located.line - 1 + CONTEXT_LINES[1]])
    task = {
        "rule": issue.rule_id,
        "wcag_criteria": issue.criteria,
        "problem": issue.title,
        "details": issue.evidence.failure_summary,
        "suggested_remedy": issue.suggested_fix or "",
        "file": located.path,
    }
    user = (
        "Fix this issue.\n"
        + untrusted_block("issue", task)
        + "\n"
        + untrusted_block("element_html", issue.evidence.html_snippet[:1500])
        + "\n"
        + raw_block("source_code", excerpt)
    )
    if feedback:
        user += f"\nA previous attempt failed verification: {feedback}. Try a different fix."
    system = f"{prompts.load('preamble')}\n\n{prompts.load('fix')}"
    try:
        proposal = await llm.complete(system=system, user=user, schema=FixProposalLLM)
    except LLMError as exc:
        return NeedsHuman(issue_id=issue.id, reason=f"fix generation failed: {exc}")
    old, new = proposal.old, proposal.new
    if old not in source and _unescape(old) in source:  # model echoed JSON-style escapes
        old, new = _unescape(old), _unescape(new)
    problem = validate_patch(source, old, new)
    if problem is not None:
        return ProposedFix(
            id=f"{issue.id}-{attempt}",
            issue_id=issue.id,
            file=located.path,
            line=located.line,
            old=old,
            new=new,
            explanation=proposal.explanation,
            diff="",
            attempt=attempt,
            status="failed",
            failure=problem,
        )
    patched = source.replace(old, new, 1)
    return ProposedFix(
        id=f"{issue.id}-{attempt}",
        issue_id=issue.id,
        file=located.path,
        line=located.line,
        old=old,
        new=new,
        explanation=proposal.explanation,
        diff=unified_diff(located.path, source, patched),
        attempt=attempt,
    )


def _unescape(text: str) -> str:
    return text.replace("\\u003c", "<").replace("\\u003e", ">").replace('\\"', '"')


Recheck = Callable[[Browser, str, Issue], Awaitable[bool]]


def is_axe_issue(issue: Issue) -> bool:
    """Issues raised by axe-core (as opposed to Ramp's own judgment-based checks)."""
    return not issue.rule_id.startswith("ramp-")


class RenderSnapshot(BaseModel):
    status: int | None
    errors: list[str]
    text_length: int
    rule_counts: dict[str, int]
    rule_keys: list[tuple[str, str]]
    screenshot: bytes = Field(exclude=True)


async def snapshot(browser: Browser, url: str) -> RenderSnapshot:
    from ramp.checks.probes import CSS_PATH_JS

    context = await new_readonly_context(
        browser, "RampA11yBot/verify", (1280, 900), [0], allowed_origins=frozenset({origin_of(url)})
    )
    errors: list[str] = []
    try:
        page = await context.new_page()
        page.on("pageerror", lambda exc: errors.append(str(exc)[:200]))
        response = await page.goto(url, wait_until="load")
        results = await run_axe(page)
        issues = violations_to_issues(results, url)
        keys: dict[str, str] = await page.evaluate(
            "(sels) => {"
            + CSS_PATH_JS
            + """
              const out = {};
              for (const s of sels) { try { const el = document.querySelector(s);
                out[s] = el ? (el === document.documentElement ? 'html' : cssPath(el)) : s; }
                catch (e) { out[s] = s; } }
              return out; }""",
            [i.selector for i in issues],
        )
        text_length = await page.evaluate("document.body ? document.body.innerText.length : 0")
        shot = await page.screenshot(full_page=True)
    finally:
        await context.close()
    return RenderSnapshot(
        status=response.status if response else None,
        errors=errors,
        text_length=int(text_length),
        rule_counts=dict(Counter(i.rule_id for i in issues)),
        rule_keys=[(i.rule_id, keys.get(i.selector, i.selector)) for i in issues],
        screenshot=shot,
    )


def pixel_diff_ratio(a: bytes, b: bytes) -> float:
    with Image.open(io.BytesIO(a)) as ia, Image.open(io.BytesIO(b)) as ib:
        width, height = max(ia.width, ib.width), max(ia.height, ib.height)
        ca = Image.new("RGB", (width, height), "white")
        cb = Image.new("RGB", (width, height), "white")
        ca.paste(ia.convert("RGB"))
        cb.paste(ib.convert("RGB"))
        diff = ImageChops.difference(ca, cb).convert("L").point(lambda v: 255 if v > 16 else 0)
        return diff.histogram()[255] / (width * height)


async def verify_fix(
    browser: Browser,
    fix: ProposedFix,
    issue: Issue,
    site_root: Path,
    page_url: str,
    before: RenderSnapshot,
    recheck: Recheck | None = None,
) -> ProposedFix:
    """Apply ``fix`` to a copy of ``site_root`` and check it (see module docstring)."""
    path = urlsplit(page_url).path
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "site"
        shutil.copytree(site_root, copy)
        target = copy / fix.file
        source = target.read_text(encoding="utf-8")
        target.write_text(source.replace(fix.old, fix.new, 1), encoding="utf-8")
        with StaticServer(copy) as server:
            url = f"{server.url}{path}"
            after = await snapshot(browser, url)
            if is_axe_issue(issue):
                # Gone means: not on that element any more AND one fewer of that rule overall
                # (element paths can shift when the fix changes markup).
                key = issue.element_key or issue.selector
                fewer = after.rule_counts.get(issue.rule_id, 0) < before.rule_counts.get(
                    issue.rule_id, 0
                )
                gone = (issue.rule_id, key) not in after.rule_keys and fewer
            elif recheck is not None:
                gone = await recheck(browser, url, issue)
            else:
                gone = False
    new_violations = [
        rule for rule, n in after.rule_counts.items() if n > before.rule_counts.get(rule, 0)
    ]
    renders = (
        after.status == 200
        and not after.errors
        and after.text_length >= 0.5 * max(1, before.text_length)
    )
    fix.violation_gone = gone
    fix.no_new_violations = not new_violations
    fix.renders = renders
    fix.visual_diff_ratio = round(pixel_diff_ratio(before.screenshot, after.screenshot), 4)
    if gone and not new_violations and renders:
        fix.status = "verified"
    else:
        reasons = []
        if not gone:
            reasons.append("the violation is still detected")
        if new_violations:
            reasons.append(f"new violations: {', '.join(new_violations)}")
        if not renders:
            reasons.append(
                f"page did not render cleanly (status {after.status}, {after.errors[:1]})"
            )
        fix.status = "failed"
        fix.failure = "; ".join(reasons)
    return fix
