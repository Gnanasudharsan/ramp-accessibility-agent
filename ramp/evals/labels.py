"""Versioned ground-truth label schema (``benchmark/schema/labels-v1.schema.json``).

Two granularities:
- **Element labels** (synthetic and adversarial pages): one barrier on one element, keyed by a
  unique CSS selector and a primary WCAG criterion. Labels on a page are complete for every
  A/AA criterion; see ``docs/labeling-guidelines.md``.
- **Page-criterion labels** (W3C BAD): the set of WCAG 2.0 A/AA criteria a page fails, taken from
  W3C's own annotations, optionally extended with failures a labeler verified by hand.
"""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ramp.checks.wcag import CRITERIA

LABEL_SCHEMA_VERSION: Literal["1.0"] = "1.0"


class DetectableBy(StrEnum):
    """Which kind of check can find the barrier without a human."""

    RULE = "rule"  # a deterministic rule engine (axe-core) finds it
    VISION = "vision"  # needs semantic judgment over the rendered page (VLM + DOM context)
    MANUAL = "manual"  # needs a human with assistive technology


class InjectionGoal(StrEnum):
    SUPPRESS_FINDINGS = "suppress_findings"
    EXFILTRATE_CANARY = "exfiltrate_canary"
    TOOL_ABUSE = "tool_abuse"
    DOWNGRADE_SEVERITY = "downgrade_severity"


class Injection(BaseModel):
    """A prompt injection planted in a page. Any appearance of ``canary`` in text the system
    generates (not in evidence copied from the page) means the injection worked."""

    canary: str = Field(pattern=r"^RAMP-CANARY-[0-9A-F]{6}$")
    vector: Literal[
        "alt", "hidden_div", "html_comment", "aria_label", "visible_text", "title", "image_text",
        "link_text", "delimiter_escape", "meta",
    ]  # fmt: skip
    goal: InjectionGoal
    payload: str


class ElementLabel(BaseModel):
    id: str
    criterion: str
    also: list[str] = Field(default_factory=list)  # other criteria the same barrier fails
    selector: str
    detectable_by: DetectableBy
    description: str
    fix_hint: str = ""

    @field_validator("criterion")
    @classmethod
    def _known_criterion(cls, value: str) -> str:
        if value not in CRITERIA:
            raise ValueError(f"unknown or out-of-scope criterion {value}")
        return value

    @property
    def criteria(self) -> set[str]:
        return {self.criterion, *self.also}


class PageLabels(BaseModel):
    page: str  # path relative to benchmark/
    set: Literal["synthetic", "adversarial"]
    title: str
    labels: list[ElementLabel] = Field(default_factory=list)
    injection: Injection | None = None
    smoke: bool = False  # part of the fast CI subset


class CriterionLabel(BaseModel):
    criterion: str
    source: Literal["w3c", "labeler"]
    note: str  # W3C note title, or the labeler's verification


class BadPageLabels(BaseModel):
    page: str  # e.g. "before/home"
    annotated_url: str | None
    scored_version: Literal["2.0"] = "2.0"
    fails: list[CriterionLabel] = Field(default_factory=list)
    out_of_scope_notes: list[str] = Field(default_factory=list)  # AAA or guideline-level notes
    smoke: bool = False


class ElementLabelSet(BaseModel):
    schema_version: Literal["1.0"] = LABEL_SCHEMA_VERSION
    pages: list[PageLabels]


class BadLabelSet(BaseModel):
    schema_version: Literal["1.0"] = LABEL_SCHEMA_VERSION
    source: str
    pages: list[BadPageLabels]


def load_element_labels(path: Path) -> ElementLabelSet:
    return ElementLabelSet.model_validate_json(path.read_text(encoding="utf-8"))


def load_bad_labels(path: Path) -> BadLabelSet:
    return BadLabelSet.model_validate_json(path.read_text(encoding="utf-8"))


def json_schema() -> str:
    """Combined JSON Schema for both label files (committed; a test keeps it in sync)."""
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": f"Ramp benchmark labels v{LABEL_SCHEMA_VERSION}",
        "oneOf": [ElementLabelSet.model_json_schema(), BadLabelSet.model_json_schema()],
    }
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"
