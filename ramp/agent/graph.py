"""The Ramp audit agent as a LangGraph state machine.

    plan → crawl → rule_checks → vision_checks → merge_and_dedupe → prioritize
         → generate_fixes ⇄ verify_fixes (max 2 attempts per issue) → human_review → open_pr

State holds only serialisable data (screenshots and crops are files under ``out_dir``), so a
checkpointed audit resumes after a crash or after the human-review interrupt. Live resources
(browser, model clients) are passed through ``config["configurable"]["runtime"]``.

Each node declares the tools it may use (``NODE_TOOLS``); every tool use is recorded and checked
against that allowlist, so a page that talks a model into "calling a tool" cannot widen what a
node can do.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from playwright.async_api import Browser, Page
from pydantic import BaseModel, Field

from ramp.agent.collect import PageEvidence, collect_evidence
from ramp.agent.fixes import (
    NeedsHuman,
    ProposedFix,
    RenderSnapshot,
    is_axe_issue,
    propose_fix,
    snapshot,
    verify_fix,
)
from ramp.agent.vision import VisionChecker
from ramp.checks.axe import (
    AXE_TAGS,
    AxeResults,
    axe_rule_metadata,
    criteria_covered_by_rules,
    run_axe,
    violations_to_issues,
)
from ramp.checks.probes import CSS_PATH_JS
from ramp.checks.wcag import CRITERIA
from ramp.config import get_settings
from ramp.crawler.crawler import CrawlConfig, PageVisit, crawl
from ramp.crawler.urls import normalize
from ramp.evals.static_server import StaticServer
from ramp.models.llm import StructuredLLM, Transcript
from ramp.report.schema import Coverage, DetectionSource, Issue, PageResult

log = logging.getLogger(__name__)

MAX_FIX_ATTEMPTS = 2

NODE_TOOLS: dict[str, frozenset[str]] = {
    "plan": frozenset(),
    "crawl": frozenset({"browser.navigate", "run_axe", "collect_evidence"}),
    "rule_checks": frozenset(),
    "vision_checks": frozenset({"llm.vision", "llm.text"}),
    "merge_and_dedupe": frozenset(),
    "prioritize": frozenset(),
    "generate_fixes": frozenset({"map_to_source", "llm.text"}),
    "verify_fixes": frozenset({"browser.navigate", "run_axe", "llm.vision", "llm.text"}),
    "human_review": frozenset(),
    "open_pr": frozenset({"github.create_branch", "github.commit", "github.open_pr"}),
}


class ToolUse(BaseModel):
    node: str
    tool: str
    target: str = ""
    allowed: bool = True


class AuditState(BaseModel):
    # inputs
    url: str
    out_dir: str
    repo_path: str | None = None  # source tree; for static sites also the served root
    max_pages: int = 5
    max_depth: int = 1
    offline: bool = False
    review_mode: Literal["interrupt", "auto_reject", "auto_approve"] = "interrupt"
    max_fixes: int = 40
    # progress
    plan: dict[str, Any] = Field(default_factory=dict)
    pages: list[PageResult] = Field(default_factory=list)
    axe: dict[str, dict[str, Any]] = Field(default_factory=dict)  # raw axe JSON per page
    axe_keys: dict[str, dict[str, str]] = Field(default_factory=dict)
    evidence: dict[str, PageEvidence] = Field(default_factory=dict)
    coverage: Coverage | None = None
    skipped: dict[str, str] = Field(default_factory=dict)
    rule_issues: list[Issue] = Field(default_factory=list)
    vision_issues: list[Issue] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    fixes: list[ProposedFix] = Field(default_factory=list)
    needs_human: list[NeedsHuman] = Field(default_factory=list)
    approved_fix_ids: list[str] = Field(default_factory=list)
    pr: dict[str, Any] | None = None
    transcript: Transcript = Field(default_factory=Transcript)
    tool_uses: list[ToolUse] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


@dataclass
class AgentRuntime:
    """Non-serialisable dependencies, rebuilt on resume."""

    browser: Browser
    transcript: Transcript = field(default_factory=Transcript)
    vision_model: str = field(default_factory=lambda: get_settings().vision_model)
    text_model: str = field(default_factory=lambda: get_settings().text_model)

    def bind(self, state: AuditState) -> tuple[StructuredLLM, StructuredLLM]:
        """Continue the state's transcript so usage accumulates across nodes and resumes."""
        self.transcript = state.transcript.model_copy(deep=True)
        return (
            StructuredLLM(self.vision_model, self.transcript),
            StructuredLLM(self.text_model, self.transcript),
        )


def _runtime(config: RunnableConfig) -> AgentRuntime:
    runtime: AgentRuntime = config["configurable"]["runtime"]
    return runtime


def _use(node: str, tool: str, target: str = "") -> ToolUse:
    allowed = tool in NODE_TOOLS[node]
    if not allowed:
        log.error("tool %s is not allowed in node %s", tool, node)
    return ToolUse(node=node, tool=tool, target=target[:200], allowed=allowed)


# --------------------------------------------------------------------------------------------
# Nodes
# --------------------------------------------------------------------------------------------


async def plan(state: AuditState) -> dict[str, Any]:
    url = normalize(state.url)
    if url is None:
        return {"errors": [*state.errors, f"not an http(s) URL: {state.url}"]}
    settings = get_settings()
    checks = ["axe-core", "image-alternatives", "link-purpose", "visual-structure", "focus-visible"]
    return {
        "url": url,
        "plan": {
            "checks": checks,
            "max_pages": min(state.max_pages, settings.max_pages),
            "max_depth": state.max_depth,
            "fixes": bool(state.repo_path) and state.max_fixes > 0,
            "review_mode": state.review_mode,
        },
    }


async def crawl_node(state: AuditState, config: RunnableConfig) -> dict[str, Any]:
    rt = _runtime(config)
    out_dir = Path(state.out_dir)
    settings = get_settings()
    pages: list[PageResult] = []
    axe: dict[str, dict[str, Any]] = {}
    keys: dict[str, dict[str, str]] = {}
    evidence: dict[str, PageEvidence] = {}
    uses: list[ToolUse] = []
    coverage: Coverage | None = None

    async def on_page(page: Page, visit: PageVisit) -> None:
        nonlocal coverage
        url = visit.final_url
        uses.append(_use("crawl", "browser.navigate", url))
        uses.append(_use("crawl", "run_axe", url))
        results = await run_axe(page)
        axe[url] = results.model_dump(mode="json", by_alias=True)
        selectors = [i.selector for i in violations_to_issues(results, url)]
        keys[url] = await page.evaluate(
            "(sels) => {"
            + CSS_PATH_JS
            + """
              const out = {};
              for (const s of sels) { try { const el = document.querySelector(s);
                if (el) out[s] = el === document.documentElement ? 'html' : cssPath(el); }
                catch (e) {} }
              return out; }""",
            selectors,
        )
        uses.append(_use("crawl", "collect_evidence", url))
        ev = await collect_evidence(page, max_images=settings.max_images_per_page)
        ev.save_images(out_dir, f"page-{len(evidence):03d}")
        evidence[url] = ev
        if coverage is None:
            rules = await axe_rule_metadata(page)
            checked = criteria_covered_by_rules(rules)
            for extra in (
                "1.1.1",
                "1.2.1",
                "1.2.2",
                "1.3.1",
                "1.3.3",
                "1.4.1",
                "1.4.5",
                "2.4.4",
                "2.4.7",
            ):
                if extra not in checked:
                    checked.append(extra)
            checked = [c for c in CRITERIA if c in checked]
            coverage = Coverage(
                axe_version=results.axe_version,
                axe_tags=AXE_TAGS,
                axe_rules_run=len(rules),
                criteria_checked=checked,
                criteria_not_checked=[c for c in CRITERIA if c not in checked],
                notes=[
                    "Judgment-based checks (image alternatives, link purpose, visual structure, "
                    "captions cues) use a vision-language model and can be wrong; each finding "
                    "carries a confidence and its evidence.",
                    "Focus visibility is checked by comparing focused and unfocused pixels.",
                    "Only rendered pages reachable by same-origin links were audited.",
                ],
            )
        pages.append(
            PageResult(
                url=visit.url,
                final_url=url,
                title=visit.title,
                depth=visit.depth,
                status=visit.status,
                screenshot=visit.screenshot,
                dom_snapshot=visit.dom_snapshot,
                needs_review=sum(len(r.nodes) for r in results.incomplete),
            )
        )

    cfg = CrawlConfig(
        start_url=state.url,
        user_agent=settings.user_agent,
        max_pages=state.plan.get("max_pages", state.max_pages),
        max_depth=state.max_depth,
        offline=state.offline,
    )
    result = await crawl(rt.browser, cfg, out_dir, on_page=on_page)
    errors = [f"{v.url}: {v.error}" for v in result.visits if v.error]
    return {
        "pages": pages,
        "axe": axe,
        "axe_keys": keys,
        "evidence": evidence,
        "coverage": coverage,
        "skipped": result.skipped,
        "tool_uses": [*state.tool_uses, *uses],
        "errors": [*state.errors, *errors],
    }


async def rule_checks(state: AuditState) -> dict[str, Any]:
    issues: list[Issue] = []
    for url, raw in state.axe.items():
        for issue in violations_to_issues(AxeResults.model_validate(raw), url):
            issue.element_key = state.axe_keys.get(url, {}).get(issue.selector, issue.selector)
            issues.append(issue)
    return {"rule_issues": issues}


async def vision_checks(state: AuditState, config: RunnableConfig) -> dict[str, Any]:
    rt = _runtime(config)
    vision, text = rt.bind(state)
    settings = get_settings()
    checker = VisionChecker(vision, text, Path(state.out_dir), settings.vision_min_confidence)
    issues: list[Issue] = []
    uses = [*state.tool_uses]
    for url, evidence in state.evidence.items():
        uses += [_use("vision_checks", "llm.vision", url), _use("vision_checks", "llm.text", url)]
        issues += await checker.check_page(evidence, url)
    return {"vision_issues": issues, "transcript": rt.transcript, "tool_uses": uses}


def _overlap(a: Issue, b: Issue) -> bool:
    return (
        a.page_url == b.page_url
        and (a.element_key or a.selector) == (b.element_key or b.selector)
        and bool(set(a.criteria) & set(b.criteria))
    )


async def merge_and_dedupe(state: AuditState) -> dict[str, Any]:
    """Rule + vision findings on the same element and criterion become one issue (source both)."""
    merged = [issue.model_copy(deep=True) for issue in state.rule_issues]
    for v in state.vision_issues:
        match = next((r for r in merged if _overlap(r, v)), None)
        if match is None:
            merged.append(v)
            continue
        if match.source is DetectionSource.RULE and v.source is DetectionSource.VISION:
            match.source = DetectionSource.BOTH
        match.suggested_fix = match.suggested_fix or v.suggested_fix
        if v.evidence.failure_summary:
            match.evidence.failure_summary += f"\nModel review: {v.evidence.failure_summary}"
    return {"issues": merged}


async def prioritize(state: AuditState) -> dict[str, Any]:
    """Deterministic order: severity, then in-target criteria first, then rule and page."""

    def key(issue: Issue) -> tuple[int, int, str, str]:
        in_target = any(CRITERIA[c].in_target for c in issue.criteria if c in CRITERIA)
        return (issue.severity.rank, 0 if in_target else 1, issue.rule_id, issue.page_url)

    return {"issues": sorted(state.issues, key=key)}


def _attempts(state: AuditState, issue_id: str) -> int:
    return sum(1 for f in state.fixes if f.issue_id == issue_id)


async def generate_fixes(state: AuditState, config: RunnableConfig) -> dict[str, Any]:
    if not state.plan.get("fixes") or state.repo_path is None:
        return {}
    rt = _runtime(config)
    _, text = rt.bind(state)
    repo = Path(state.repo_path)
    fixes, needs_human = list(state.fixes), list(state.needs_human)
    uses = [*state.tool_uses]
    done = {f.issue_id for f in fixes if f.status == "verified"} | {n.issue_id for n in needs_human}
    targets = [i for i in state.issues if i.criteria and i.id not in done][: state.max_fixes]
    for issue in targets:
        attempts = _attempts(state, issue.id)
        last = next((f for f in reversed(fixes) if f.issue_id == issue.id), None)
        if last is not None and last.status != "failed":
            continue  # proposed or verified already
        if attempts >= MAX_FIX_ATTEMPTS:
            needs_human.append(
                NeedsHuman(issue_id=issue.id, reason=f"{attempts} fixes failed verification")
            )
            continue
        uses += [
            _use("generate_fixes", "map_to_source", issue.selector),
            _use("generate_fixes", "llm.text", issue.id),
        ]
        feedback = last.failure if last is not None else None
        result = await propose_fix(text, issue, repo, feedback=feedback, attempt=attempts + 1)
        if isinstance(result, NeedsHuman):
            needs_human.append(result)
        else:
            fixes.append(result)
    return {
        "fixes": fixes,
        "needs_human": needs_human,
        "transcript": rt.transcript,
        "tool_uses": uses,
    }


async def verify_fixes(state: AuditState, config: RunnableConfig) -> dict[str, Any]:
    pending = [f for f in state.fixes if f.status == "proposed"]
    if not pending or state.repo_path is None:
        return {}
    rt = _runtime(config)
    vision, text = rt.bind(state)
    checker = VisionChecker(vision, text, Path(state.out_dir), 0.0)
    settings = get_settings()
    site_root = Path(state.repo_path)
    by_id = {i.id: i for i in state.issues}
    uses = [*state.tool_uses]
    befores: dict[str, RenderSnapshot] = {}

    async def recheck(browser: Browser, url: str, issue: Issue) -> bool:
        """Re-run the judgment-based check on the patched page; True if the issue is gone."""
        uses.append(_use("verify_fixes", "llm.vision", issue.id))
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            await page.goto(url, wait_until="load")
            evidence = await collect_evidence(page, max_images=settings.max_images_per_page)
        finally:
            await page.close()
        evidence.save_images(Path(state.out_dir), f"verify-{issue.id}")
        return not await checker.recheck_element(evidence, issue)

    updated: list[ProposedFix] = []
    for fix in state.fixes:
        if fix.status != "proposed":
            updated.append(fix)
            continue
        issue = by_id[fix.issue_id]
        path = urlsplit(issue.page_url).path
        if path not in befores:
            with StaticServer(site_root) as server:
                uses.append(_use("verify_fixes", "browser.navigate", path))
                befores[path] = await snapshot(rt.browser, f"{server.url}{path}")
        uses.append(_use("verify_fixes", "run_axe", path))
        checked = await verify_fix(
            rt.browser,
            fix.model_copy(deep=True),
            issue,
            site_root,
            issue.page_url,
            befores[path],
            recheck=None if is_axe_issue(issue) else recheck,
        )
        updated.append(checked)
    return {"fixes": updated, "transcript": rt.transcript, "tool_uses": uses}


def after_verify(state: AuditState) -> str:
    """Loop back to repair while some issue's latest fix failed and attempts remain."""
    latest: dict[str, ProposedFix] = {}
    for fix in state.fixes:
        latest[fix.issue_id] = fix
    retry = any(
        f.status == "failed" and _attempts(state, issue_id) < MAX_FIX_ATTEMPTS
        for issue_id, f in latest.items()
    )
    return "generate_fixes" if retry else "human_review"


async def human_review(state: AuditState) -> dict[str, Any]:
    verified = [f for f in state.fixes if f.status == "verified"]
    if not verified:
        return {"approved_fix_ids": []}
    if state.review_mode == "auto_reject":
        return {"approved_fix_ids": []}
    if state.review_mode == "auto_approve":
        return {"approved_fix_ids": [f.id for f in verified]}
    decision = interrupt(
        {
            "message": "Approve the exact diffs to include in the pull request.",
            "fixes": [
                {"id": f.id, "file": f.file, "diff": f.diff, "explanation": f.explanation}
                for f in verified
            ],
        }
    )
    approved = set(decision.get("approved", [])) if isinstance(decision, dict) else set()
    approve_all = "*" in approved
    return {"approved_fix_ids": [f.id for f in verified if approve_all or f.id in approved]}


async def open_pr(state: AuditState) -> dict[str, Any]:
    """Phase 3: write the approved, verified diffs as one patch. Phase 4 opens the GitHub PR."""
    approved = [f for f in state.fixes if f.id in set(state.approved_fix_ids)]
    if not approved:
        return {"pr": {"status": "nothing_approved"}}
    patch = Path(state.out_dir) / "ramp-fixes.patch"
    patch.write_text("".join(f.diff for f in approved), encoding="utf-8")
    return {"pr": {"status": "patch_written", "patch": str(patch), "fixes": len(approved)}}


def build_graph() -> StateGraph[AuditState]:
    graph = StateGraph(AuditState)
    graph.add_node("plan", plan)
    graph.add_node("crawl", crawl_node)
    graph.add_node("rule_checks", rule_checks)
    graph.add_node("vision_checks", vision_checks)
    graph.add_node("merge_and_dedupe", merge_and_dedupe)
    graph.add_node("prioritize", prioritize)
    graph.add_node("generate_fixes", generate_fixes)
    graph.add_node("verify_fixes", verify_fixes)
    graph.add_node("human_review", human_review)
    graph.add_node("open_pr", open_pr)
    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", lambda s: END if s.errors else "crawl")
    graph.add_edge("crawl", "rule_checks")
    graph.add_edge("rule_checks", "vision_checks")
    graph.add_edge("vision_checks", "merge_and_dedupe")
    graph.add_edge("merge_and_dedupe", "prioritize")
    graph.add_edge("prioritize", "generate_fixes")
    graph.add_edge("generate_fixes", "verify_fixes")
    graph.add_conditional_edges("verify_fixes", after_verify)
    graph.add_edge("human_review", "open_pr")
    graph.add_edge("open_pr", END)
    return graph
