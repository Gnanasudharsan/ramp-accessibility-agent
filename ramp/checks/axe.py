"""Run axe-core inside a Playwright page and convert its output to Ramp issues.

axe-core is vendored (``vendor/axe.min.js``, MPL-2.0) so the rule set is pinned and audits are
reproducible. The run options here are the contract that the reproduction test checks against
Deque's own ``@axe-core/playwright`` integration (``benchmark/reference``).
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

from playwright.async_api import Page
from pydantic import BaseModel, Field

from ramp.checks.wcag import CRITERIA, criteria_from_axe_tags
from ramp.report.schema import DetectionSource, Evidence, Issue, Severity

AXE_PATH = Path(__file__).parent / "vendor" / "axe.min.js"

# WCAG 2.0/2.1/2.2 A and AA rules plus axe best practices (reported, but never as WCAG failures).
AXE_TAGS: list[str] = [
    "wcag2a",
    "wcag2aa",
    "wcag21a",
    "wcag21aa",
    "wcag22aa",
    "best-practice",
]


@cache
def axe_source() -> str:
    return AXE_PATH.read_text(encoding="utf-8")


class AxeNode(BaseModel):
    target: list[Any]  # strings, or nested lists for iframes / shadow DOM
    html: str
    failure_summary: str = Field(default="", alias="failureSummary")
    impact: str | None = None


class AxeRuleResult(BaseModel):
    id: str
    impact: str | None = None
    tags: list[str]
    help: str
    help_url: str = Field(alias="helpUrl")
    nodes: list[AxeNode]


class AxeResults(BaseModel):
    """The subset of ``axe.run`` output Ramp uses."""

    axe_version: str
    url: str
    violations: list[AxeRuleResult]
    incomplete: list[AxeRuleResult]


async def inject_axe(page: Page) -> None:
    """Inject axe into every frame so ``axe.run`` can descend into iframes."""
    source = axe_source()
    for frame in page.frames:
        try:
            await frame.evaluate(source)
        except Exception:  # noqa: S112 - a detached/cross-process frame is skipped, not fatal
            continue


async def run_axe(page: Page, tags: list[str] | None = None) -> AxeResults:
    """Run axe-core on the current page with the pinned options."""
    await inject_axe(page)
    options = {
        "runOnly": {"type": "tag", "values": tags or AXE_TAGS},
        "resultTypes": ["violations", "incomplete"],
    }
    raw: dict[str, Any] = await page.evaluate(
        """async (options) => {
            const r = await axe.run(document, options);
            return {
              axe_version: r.testEngine.version,
              url: r.url,
              violations: r.violations,
              incomplete: r.incomplete,
            };
        }""",
        options,
    )
    return AxeResults.model_validate(raw)


async def axe_rule_metadata(page: Page, tags: list[str] | None = None) -> list[dict[str, Any]]:
    """Rules axe would run for the given tags (used to state report coverage)."""
    await inject_axe(page)
    rules: list[dict[str, Any]] = await page.evaluate(
        "(tags) => axe.getRules(tags).map(r => ({ruleId: r.ruleId, tags: r.tags}))",
        tags or AXE_TAGS,
    )
    return rules


def target_to_selector(target: list[Any]) -> str:
    """Flatten an axe target to one string. Nested lists (iframe / shadow DOM) join with ' >>> '."""
    parts: list[str] = []
    for item in target:
        parts.append(" >>> ".join(item) if isinstance(item, list) else str(item))
    return " ".join(parts)


def _severity(impact: str | None) -> Severity:
    try:
        return Severity(impact or "minor")
    except ValueError:
        return Severity.MINOR


def violations_to_issues(results: AxeResults, page_url: str) -> list[Issue]:
    """One Issue per (rule, node). Lossless: every violating node becomes exactly one issue."""
    issues: list[Issue] = []
    for rule in results.violations:
        criteria = criteria_from_axe_tags(rule.tags)
        for node in rule.nodes:
            selector = target_to_selector(node.target)
            issues.append(
                Issue(
                    id=Issue.make_id(page_url, rule.id, selector),
                    rule_id=rule.id,
                    title=rule.help,
                    criteria=criteria,
                    severity=_severity(node.impact or rule.impact),
                    page_url=page_url,
                    selector=selector,
                    evidence=Evidence(
                        html_snippet=node.html[:4000], failure_summary=node.failure_summary
                    ),
                    source=DetectionSource.RULE,
                    confidence=1.0,
                    help_url=rule.help_url,
                )
            )
    return issues


def criteria_covered_by_rules(rules: list[dict[str, Any]]) -> list[str]:
    """Success criteria with at least one axe rule, in catalog order."""
    covered = {c for rule in rules for c in criteria_from_axe_tags(rule["tags"])}
    return [cid for cid in CRITERIA if cid in covered]
