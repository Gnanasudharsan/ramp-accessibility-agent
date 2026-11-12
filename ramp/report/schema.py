"""Pydantic schema for audit reports. Version it: downstream evals and the web UI read it."""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

REPORT_SCHEMA_VERSION = "1.1"

DISCLAIMER = (
    "Automated testing finds only part of WCAG issues. This report is not a statement of "
    "compliance. It lists what was checked and what was not; test with assistive technology "
    "(for example VoiceOver, NVDA, keyboard only) and with disabled users before drawing "
    "conclusions."
)


class Severity(StrEnum):
    """axe-core impact levels, reused for vision findings."""

    CRITICAL = "critical"
    SERIOUS = "serious"
    MODERATE = "moderate"
    MINOR = "minor"

    @property
    def rank(self) -> int:
        return ["critical", "serious", "moderate", "minor"].index(self.value)


class DetectionSource(StrEnum):
    RULE = "rule"
    VISION = "vision"
    BOTH = "both"


class BoundingBox(BaseModel):
    x: float
    y: float
    width: float
    height: float


class Evidence(BaseModel):
    """What a reviewer needs to confirm an issue without re-running the audit."""

    html_snippet: str = Field(max_length=4000)
    failure_summary: str = ""
    screenshot_crop: str | None = None  # path relative to the report directory
    bounding_box: BoundingBox | None = None


class Issue(BaseModel):
    """One barrier on one element."""

    id: str
    rule_id: str
    title: str
    criteria: list[str] = Field(default_factory=list)  # e.g. ["1.1.1"]; empty = best practice
    severity: Severity
    page_url: str
    selector: str
    evidence: Evidence
    source: DetectionSource
    confidence: float = Field(ge=0.0, le=1.0)
    help_url: str | None = None
    element_key: str | None = None  # canonical element path, used to merge rule and vision findings
    suggested_fix: str | None = None

    @staticmethod
    def make_id(page_url: str, rule_id: str, selector: str) -> str:
        """Stable id so the same barrier keeps its id across runs (used for dedupe and diffs)."""
        digest = hashlib.sha256(f"{page_url}\n{rule_id}\n{selector}".encode()).hexdigest()
        return digest[:12]


class PageResult(BaseModel):
    url: str
    final_url: str
    title: str
    depth: int
    status: int | None = None
    screenshot: str | None = None
    dom_snapshot: str | None = None
    issues: list[Issue] = Field(default_factory=list)
    needs_review: int = 0  # axe "incomplete" results: a human must decide
    error: str | None = None


class Coverage(BaseModel):
    """What the audit did and did not check, derived from the tools' own metadata."""

    axe_version: str
    axe_tags: list[str]
    axe_rules_run: int
    criteria_checked: list[str]
    criteria_not_checked: list[str]
    notes: list[str] = Field(default_factory=list)


class FixSummary(BaseModel):
    """A proposed source change and how verification went."""

    id: str
    issue_id: str
    file: str
    diff: str
    explanation: str
    status: str  # verified | failed | proposed
    failure: str | None = None
    visual_diff_ratio: float | None = None
    approved: bool = False


class AuditReport(BaseModel):
    schema_version: str = REPORT_SCHEMA_VERSION
    target: str
    started_at: datetime
    finished_at: datetime
    ramp_version: str
    pages: list[PageResult]
    coverage: Coverage
    skipped_urls: dict[str, str] = Field(default_factory=dict)  # url -> reason
    fixes: list[FixSummary] = Field(default_factory=list)
    needs_human: dict[str, str] = Field(default_factory=dict)  # issue id -> reason
    model_usage: dict[str, float] = Field(default_factory=dict)
    disclaimer: str = DISCLAIMER

    @property
    def issues(self) -> list[Issue]:
        return [issue for page in self.pages for issue in page.issues]
