"""Open a pull request with approved, verified fixes through GitHub's official MCP server.

Flow (``open_pull_request``):
1. Policy: read the target repo's CONTRIBUTING / AI policy (``get_file_contents``), refuse if it
   rejects AI-generated contributions, add disclosure when required, one PR per repo (ledger).
2. Re-verify all approved fixes *together* on a copy of the site before publishing: fixes are
   verified one by one during the audit, and two individually-good fixes can still conflict.
3. ``create_branch`` → ``push_files`` (one commit with every changed file) →
   ``create_pull_request`` with a description of each fix, its WCAG criteria, verification
   results, before/after screenshots, and what was not checked.

The GitHub MCP server's file tools accept text only, so before/after PNGs are uploaded with the
Git data API to a separate ``ramp-evidence`` branch and linked from the PR body; the PR's own
branch contains only the approved source changes.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from ramp.github.policy import DISCLOSURE, POLICY_FILES, PolicyDecision, PRLedger, evaluate_policy

GITHUB_MCP_IMAGE = "ghcr.io/github/github-mcp-server:v2.1.0"
EVIDENCE_BRANCH = "ramp-evidence"


class PublishError(RuntimeError):
    pass


@dataclass
class ApprovedFix:
    id: str
    file: str
    old: str
    new: str
    explanation: str
    issue_title: str
    criteria: list[str]
    page_path: str
    visual_diff_ratio: float | None


@asynccontextmanager
async def github_mcp(token: str) -> AsyncIterator[Client]:
    """Run the official GitHub MCP server in Docker, limited to repo and PR toolsets."""
    params = StdioServerParameters(
        command="docker",
        args=[
            "run",
            "-i",
            "--rm",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "-e",
            "GITHUB_PERSONAL_ACCESS_TOKEN",
            "-e",
            "GITHUB_TOOLSETS",
            GITHUB_MCP_IMAGE,
        ],
        env={
            "GITHUB_PERSONAL_ACCESS_TOKEN": token,
            "GITHUB_TOOLSETS": "repos,pull_requests",
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        },
    )
    async with Client(params) as client:
        yield client


async def _call(client: Client, tool: str, args: dict[str, Any]) -> Any:
    result = await client.call_tool(tool, args)
    text = "".join(getattr(c, "text", "") for c in result.content)
    if result.is_error:
        raise PublishError(f"{tool} failed: {text[:400]}")
    if result.structured_content is not None:
        return result.structured_content
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


async def read_policy(client: Client, owner: str, repo: str) -> PolicyDecision:
    documents: dict[str, str] = {}
    for path in POLICY_FILES:
        try:
            data = await _call(
                client, "get_file_contents", {"owner": owner, "repo": repo, "path": path}
            )
        except PublishError:
            continue
        text = data if isinstance(data, str) else json.dumps(data)
        documents[path] = text[:20_000]
    return evaluate_policy(owner, documents)


def apply_fixes(root: Path, fixes: list[ApprovedFix]) -> tuple[dict[str, str], list[str]]:
    """Apply fixes in order to files under ``root``. Returns changed files and skipped fix ids."""
    changed: dict[str, str] = {}
    skipped: list[str] = []
    for fix in fixes:
        path = root / fix.file
        text = changed.get(fix.file) or path.read_text(encoding="utf-8")
        if text.count(fix.old) != 1:
            skipped.append(fix.id)  # an earlier fix already changed this code
            continue
        changed[fix.file] = text.replace(fix.old, fix.new, 1)
    for rel, text in changed.items():
        (root / rel).write_text(text, encoding="utf-8")
    return changed, skipped


def pr_body(
    fixes: list[ApprovedFix],
    combined: dict[str, Any],
    evidence: dict[str, tuple[str, str]],
    decision: PolicyDecision,
    not_checked: list[str],
) -> str:
    lines = [
        "This pull request fixes accessibility barriers found by "
        "[Ramp](https://github.com/Gnanasudharsan/ramp-accessibility-agent), an automated "
        "auditor. Every change below was verified on a rendered copy of the site, and a human "
        "approved the exact diff before this PR was opened.",
        "",
        "| Fix | WCAG | File | Pixels changed |",
        "|---|---|---|---:|",
    ]
    for f in fixes:
        ratio = "—" if f.visual_diff_ratio is None else f"{f.visual_diff_ratio * 100:.2f}%"
        lines.append(f"| {f.issue_title} | {', '.join(f.criteria)} | `{f.file}` | {ratio} |")
    lines += ["", "### What changed", ""]
    lines += [f"- **{f.issue_title}** (`{f.file}`): {f.explanation}" for f in fixes]
    lines += [
        "",
        "### Verification (all fixes applied together)",
        "",
        f"- Targeted violations still present: {combined['remaining']}",
        f"- New axe-core violations: {combined['new_violations'] or 'none'}",
        f"- Pages render (HTTP 200, no script errors): {'yes' if combined['renders'] else 'no'}",
    ]
    if evidence:
        lines += ["", "### Before and after", ""]
        for page, (before, after) in evidence.items():
            lines += [
                f"`{page}`",
                "",
                "| Before | After |",
                "|---|---|",
                f"| ![before]({before}) | ![after]({after}) |",
                "",
            ]
    lines += [
        "",
        "### What was not checked",
        "",
        "Automated testing finds only part of WCAG issues; this PR is not a statement of "
        "compliance. Not covered: " + (", ".join(not_checked) or "see the Ramp report") + ". "
        "Please also test with a keyboard and a screen reader.",
    ]
    if decision.disclosure_required:
        lines += ["", DISCLOSURE]
    return "\n".join(lines)


async def upload_evidence(
    token: str, owner: str, repo: str, images: dict[str, bytes], prefix: str
) -> dict[str, str]:
    """Commit PNGs to the ``ramp-evidence`` branch via the Git data API; return raw URLs."""
    api = f"https://api.github.com/repos/{owner}/{repo}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    async with httpx.AsyncClient(headers=headers, timeout=30) as gh:
        ref = await gh.get(f"{api}/git/ref/heads/{EVIDENCE_BRANCH}")
        parent = ref.json()["object"]["sha"] if ref.status_code == 200 else None
        tree = []
        for name, data in images.items():
            blob = await gh.post(
                f"{api}/git/blobs",
                json={"content": base64.b64encode(data).decode(), "encoding": "base64"},
            )
            blob.raise_for_status()
            tree.append(
                {
                    "path": f"{prefix}/{name}",
                    "mode": "100644",
                    "type": "blob",
                    "sha": blob.json()["sha"],
                }
            )
        base_tree = None
        if parent:
            base_tree = (await gh.get(f"{api}/git/commits/{parent}")).json()["tree"]["sha"]
        payload: dict[str, Any] = {"tree": tree}
        if base_tree:
            payload["base_tree"] = base_tree
        new_tree = await gh.post(f"{api}/git/trees", json=payload)
        new_tree.raise_for_status()
        commit = await gh.post(
            f"{api}/git/commits",
            json={
                "message": f"chore: Ramp evidence screenshots for {prefix}",
                "tree": new_tree.json()["sha"],
                "parents": [parent] if parent else [],
            },
        )
        commit.raise_for_status()
        sha = commit.json()["sha"]
        if parent:
            update = await gh.patch(f"{api}/git/refs/heads/{EVIDENCE_BRANCH}", json={"sha": sha})
        else:
            new_ref = {"ref": f"refs/heads/{EVIDENCE_BRANCH}", "sha": sha}
            update = await gh.post(f"{api}/git/refs", json=new_ref)
        update.raise_for_status()
    raw = f"https://raw.githubusercontent.com/{owner}/{repo}/{EVIDENCE_BRANCH}/{prefix}"
    return {name: f"{raw}/{name}" for name in images}


def _slug(page: str) -> str:
    return page.strip("/").replace("/", "_") or "index"


async def open_pull_request(
    *,
    token: str,
    owner: str,
    repo: str,
    base: str,
    site_root: Path,
    fixes: list[ApprovedFix],
    verify_combined: Any,
    not_checked: list[str],
    invited: bool = False,
    ledger: PRLedger | None = None,
) -> dict[str, Any]:
    """Run the full flow; returns {"status", "url", ...}. Never opens a PR without fixes."""
    if not fixes:
        return {"status": "nothing_approved"}
    ledger = ledger or PRLedger()
    full = f"{owner}/{repo}"
    if not ledger.may_open(full, invited=invited):
        return {"status": "refused", "reason": "a Ramp PR was already opened on this repository"}

    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "site"
        shutil.copytree(site_root, copy)
        changed, skipped = apply_fixes(copy, fixes)
        applied = [f for f in fixes if f.id not in skipped]
        combined, shots = await verify_combined(copy, applied)
    if combined["remaining"] or combined["new_violations"] or not combined["renders"]:
        return {
            "status": "refused",
            "reason": "combined fixes failed verification",
            "verification": combined,
        }

    async with github_mcp(token) as client:
        decision = await read_policy(client, owner, repo)
        if not decision.allowed:
            return {"status": "refused", "reason": decision.reason, "policy": decision.files_read}
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        branch = f"ramp/a11y-{stamp}"
        images: dict[str, bytes] = {}
        for page, (before, after) in shots.items():
            images[f"{_slug(page)}-before.png"] = before
            images[f"{_slug(page)}-after.png"] = after
        urls = await upload_evidence(token, owner, repo, images, branch.replace("/", "-"))
        evidence = {
            page: (urls[f"{_slug(page)}-before.png"], urls[f"{_slug(page)}-after.png"])
            for page in shots
        }
        branch_args = {"owner": owner, "repo": repo, "branch": branch, "from_branch": base}
        await _call(client, "create_branch", branch_args)
        n = len(applied)
        plural = "es" if n != 1 else ""
        await _call(
            client,
            "push_files",
            {
                "owner": owner,
                "repo": repo,
                "branch": branch,
                "message": f"fix(a11y): {n} accessibility fix{plural} verified by Ramp",
                "files": [{"path": p, "content": c} for p, c in sorted(changed.items())],
            },
        )
        title = f"Fix {n} accessibility barrier{'s' if n != 1 else ''} (WCAG 2.1 AA)"
        body = pr_body(applied, combined, evidence, decision, not_checked)
        pr = await _call(
            client,
            "create_pull_request",
            {
                "owner": owner,
                "repo": repo,
                "title": title,
                "head": branch,
                "base": base,
                "body": body,
                "draft": False,
            },
        )
    url = pr.get("html_url") or pr.get("url") if isinstance(pr, dict) else str(pr)
    ledger.record(full, str(url))
    return {
        "status": "opened",
        "url": url,
        "branch": branch,
        "fixes": n,
        "skipped": skipped,
        "policy": decision.reason,
    }
