"""The interface every audited system implements, and the axe-core baseline.

A system audits one page and returns issues plus everything the eval needs to judge safety:
the text it *generated* (canary checks must ignore evidence copied from the page), the tool
calls it attempted, any fixes, and its latency and cost.
"""

from __future__ import annotations

import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from playwright.async_api import Browser
from pydantic import BaseModel, Field

from ramp.audit import audit_url
from ramp.report.schema import Issue


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class FixOutcome(BaseModel):
    issue_id: str
    attempted: bool
    violation_gone: bool = False
    no_new_violations: bool = False
    renders: bool = False

    @property
    def success(self) -> bool:
        return self.attempted and self.violation_gone and self.no_new_violations and self.renders


class SystemOutput(BaseModel):
    issues: list[Issue]
    generated_text: list[str] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    fixes: list[FixOutcome] = Field(default_factory=list)
    latency_s: float = 0.0
    cost_usd: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    needs_human: int = 0
    failed_model_calls: int = 0


class AuditSystem(Protocol):
    name: str

    async def audit_page(self, url: str, browser: Browser) -> SystemOutput: ...


class AxeBaseline:
    """Phase 1 pipeline: axe-core only. No model calls, no fixes, no tools beyond the browser."""

    name = "axe-baseline"

    async def audit_page(self, url: str, browser: Browser) -> SystemOutput:
        started = time.perf_counter()
        with tempfile.TemporaryDirectory() as tmp:
            report = await audit_url(
                url,
                Path(tmp),
                user_agent="RampA11yBot/eval",
                max_pages=1,
                max_depth=0,
                browser=browser,
                offline=True,
            )
        return SystemOutput(
            issues=report.issues,
            generated_text=[i.title for i in report.issues],
            latency_s=time.perf_counter() - started,
        )


class AgentSystem:
    """The full Ramp agent (Phase 3), run per page with the benchmark site as its source repo.

    The served page and the "repository" are the same files, so fixes are patches to the very
    HTML that was audited and verification re-serves the patched copy. Review is auto-rejected:
    evals never open pull requests.
    """

    def __init__(self, name: str = "ramp-agent", fixes: bool = True, site_root: Path | None = None):
        self.name = name
        self.fixes = fixes
        self.site_root = site_root

    async def audit_page(self, url: str, browser: Browser) -> SystemOutput:
        from ramp.agent.graph import AuditState
        from ramp.agent.run import start_audit
        from ramp.config import get_settings
        from ramp.evals.static_server import StaticServer

        started = time.perf_counter()
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "out"
            repo: Path | None = None
            target = url
            server: StaticServer | None = None
            local = self.site_root / urlsplit(url).path.lstrip("/") if self.site_root else None
            if self.fixes and self.site_root is not None and local is not None and local.exists():
                repo = Path(tmp) / "repo"
                shutil.copytree(self.site_root, repo)
                server = StaticServer(repo).__enter__()
                target = f"{server.url}{urlsplit(url).path}"
            try:
                state = AuditState(
                    url=target,
                    out_dir=str(out_dir),
                    repo_path=str(repo) if repo else None,
                    max_pages=1,
                    max_depth=0,
                    offline=True,
                    review_mode="auto_reject",
                    max_fixes=get_settings().max_fixes_per_audit if repo else 0,
                )
                run = await start_audit(
                    state, f"eval-{uuid.uuid4().hex}", browser, db=Path(tmp) / "ckpt.sqlite"
                )
            finally:
                if server is not None:
                    server.__exit__(None, None, None)
        final = run.state
        wall = time.perf_counter() - started
        usage = final.transcript.usage
        latest: dict[str, FixOutcome] = {}
        for fix in final.fixes:
            latest[fix.issue_id] = FixOutcome(
                issue_id=fix.issue_id,
                attempted=True,
                violation_gone=fix.violation_gone,
                no_new_violations=fix.no_new_violations,
                renders=fix.renders,
            )
        generated = [*final.transcript.outputs]
        generated += [f"{f.explanation}\n{f.new}" for f in final.fixes]
        # Map issues back to the URL the eval asked about (the agent audited a served copy).
        issues = []
        for issue in final.issues:
            issue = issue.model_copy()
            issue.page_url = url
            issues.append(issue)
        return SystemOutput(
            issues=issues,
            generated_text=generated,
            tool_calls=[ToolCall(name=u.tool, arguments={"node": u.node}) for u in final.tool_uses],
            fixes=list(latest.values()),
            latency_s=wall + usage.replayed_latency_s,
            cost_usd=usage.cost_usd(),
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            needs_human=len(final.needs_human),
            failed_model_calls=usage.failed_calls,
        )
