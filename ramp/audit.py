"""Deterministic audit pipeline: crawl → axe-core → evidence → report.

This is the Phase 1 baseline the agent is measured against. It makes no model calls.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image
from playwright.async_api import Browser, Page, async_playwright

from ramp import __version__
from ramp.checks.axe import (
    AXE_TAGS,
    axe_rule_metadata,
    criteria_covered_by_rules,
    run_axe,
    violations_to_issues,
)
from ramp.checks.probes import element_boxes
from ramp.checks.wcag import CRITERIA
from ramp.config import get_settings
from ramp.crawler.crawler import CrawlConfig, PageVisit, crawl
from ramp.crawler.politeness import LimiterFactory
from ramp.report.schema import AuditReport, BoundingBox, Coverage, PageResult

MAX_CROPS_PER_PAGE = 60
CROP_PADDING = 8

COVERAGE_NOTES = [
    "Only rendered pages reachable by same-origin links were audited; content behind logins, "
    "forms, or user interaction was not.",
    "axe-core reports only issues it can determine automatically; 'needs review' items require a "
    "human decision.",
    "Criteria listed as not checked have no automated rule here and need manual testing.",
]


@asynccontextmanager
async def launch_browser(ws_endpoint: str | None = None) -> AsyncIterator[Browser]:
    """A local headless Chromium, or a remote one when ``ws_endpoint`` (or ``RAMP_BROWSER_WS``)
    is set: in Docker Compose the worker drives the browser in the sandbox container instead of
    running one itself (ADR 0006)."""
    endpoint = ws_endpoint or get_settings().browser_ws
    async with async_playwright() as pw:
        if endpoint:
            browser = await pw.chromium.connect(endpoint)
        else:
            browser = await pw.chromium.launch(headless=True)
        try:
            yield browser
        finally:
            await browser.close()


def crop_evidence(screenshot: Path, box: BoundingBox, dest: Path) -> bool:
    """Save a padded crop of ``box`` from a full-page screenshot. Returns False if out of bounds."""
    with Image.open(screenshot) as image:
        left = max(0, int(box.x) - CROP_PADDING)
        top = max(0, int(box.y) - CROP_PADDING)
        right = min(image.width, int(box.x + box.width) + CROP_PADDING)
        bottom = min(image.height, int(box.y + box.height) + CROP_PADDING)
        if right - left < 2 or bottom - top < 2:
            return False
        image.crop((left, top, right, bottom)).save(dest)
    return True


async def audit_url(
    url: str,
    out_dir: Path,
    *,
    user_agent: str,
    max_pages: int = 10,
    max_depth: int = 2,
    browser: Browser | None = None,
    offline: bool = False,
    on_progress: Callable[[PageResult], Awaitable[None]] | None = None,
    limiter_factory: LimiterFactory | None = None,
) -> AuditReport:
    """Crawl ``url`` and run axe-core on every page; write artifacts under ``out_dir``.

    ``on_progress`` is awaited after each page is audited (the API streams it as an event)."""
    started = datetime.now(UTC)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "evidence").mkdir(exist_ok=True)
    pages: list[PageResult] = []
    coverage: Coverage | None = None

    async def on_page(page: Page, visit: PageVisit) -> None:
        nonlocal coverage
        results = await run_axe(page)
        issues = violations_to_issues(results, visit.final_url)
        boxes = await element_boxes(page, [i.selector for i in issues[:MAX_CROPS_PER_PAGE]])
        for issue in issues[:MAX_CROPS_PER_PAGE]:
            box = boxes.get(issue.selector)
            if box is None or visit.screenshot is None:
                continue
            issue.evidence.bounding_box = box
            crop = out_dir / "evidence" / f"{issue.id}.png"
            if crop_evidence(out_dir / visit.screenshot, box, crop):
                issue.evidence.screenshot_crop = str(crop.relative_to(out_dir))
        if coverage is None:
            rules = await axe_rule_metadata(page)
            checked = criteria_covered_by_rules(rules)
            coverage = Coverage(
                axe_version=results.axe_version,
                axe_tags=AXE_TAGS,
                axe_rules_run=len(rules),
                criteria_checked=checked,
                criteria_not_checked=[c for c in CRITERIA if c not in checked],
                notes=COVERAGE_NOTES,
            )
        pages.append(
            PageResult(
                url=visit.url,
                final_url=visit.final_url,
                title=visit.title,
                depth=visit.depth,
                status=visit.status,
                screenshot=visit.screenshot,
                dom_snapshot=visit.dom_snapshot,
                issues=issues,
                needs_review=sum(len(r.nodes) for r in results.incomplete),
            )
        )
        if on_progress is not None:
            await on_progress(pages[-1])

    config = CrawlConfig(
        start_url=url,
        user_agent=user_agent,
        max_pages=max_pages,
        max_depth=max_depth,
        offline=offline,
    )
    if browser is None:
        async with launch_browser() as owned:
            result = await crawl(
                owned, config, out_dir, on_page=on_page, limiter_factory=limiter_factory
            )
    else:
        result = await crawl(
            browser, config, out_dir, on_page=on_page, limiter_factory=limiter_factory
        )

    audited = {p.url for p in pages}
    for visit in result.visits:
        if visit.url not in audited and visit.error:
            pages.append(
                PageResult(
                    url=visit.url,
                    final_url=visit.final_url,
                    title=visit.title,
                    depth=visit.depth,
                    error=visit.error,
                )
            )
    return AuditReport(
        target=url,
        started_at=started,
        finished_at=datetime.now(UTC),
        ramp_version=__version__,
        pages=pages,
        coverage=coverage
        or Coverage(
            axe_version="unknown",
            axe_tags=AXE_TAGS,
            axe_rules_run=0,
            criteria_checked=[],
            criteria_not_checked=list(CRITERIA),
            notes=[*COVERAGE_NOTES, "No page could be audited."],
        ),
        skipped_urls=result.skipped,
    )
