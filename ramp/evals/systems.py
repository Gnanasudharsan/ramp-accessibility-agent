"""The interface every audited system implements, and the axe-core baseline.

A system audits one page and returns issues plus everything the eval needs to judge safety:
the text it *generated* (canary checks must ignore evidence copied from the page), the tool
calls it attempted, any fixes, and its latency and cost.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any, Protocol

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
