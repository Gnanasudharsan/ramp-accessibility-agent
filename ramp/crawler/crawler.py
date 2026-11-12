"""Polite, read-only, same-origin crawler built on Playwright.

Guarantees (see CLAUDE.md, ethics section):
- robots.txt is honoured for every page URL; the crawl delay is max(1 s, Crawl-delay).
- At most one page navigation per second per host.
- Read-only: every non-GET/HEAD request is aborted at the network layer, so no form can be
  submitted and no state-changing call can be made, even by page scripts. Downloads and service
  workers are disabled.
- Same-origin only, with depth and page caps.
"""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from playwright.async_api import Browser, BrowserContext, Page, Route

from ramp.crawler.politeness import RateLimiter, RobotsPolicy
from ramp.crawler.urls import normalize, origin_of, same_origin

log = logging.getLogger(__name__)

READ_ONLY_METHODS = frozenset({"GET", "HEAD"})
NAV_TIMEOUT_MS = 30_000


@dataclass(frozen=True)
class CrawlConfig:
    start_url: str
    user_agent: str
    max_pages: int = 10
    max_depth: int = 2
    min_interval: float = 1.0
    viewport: tuple[int, int] = (1280, 900)
    offline: bool = False  # block every request outside the start URL's origin


@dataclass
class PageVisit:
    """A page that was loaded, with paths to its artifacts (relative to the output dir)."""

    url: str
    final_url: str
    depth: int
    title: str = ""
    status: int | None = None
    screenshot: str | None = None
    dom_snapshot: str | None = None
    error: str | None = None


@dataclass
class CrawlResult:
    visits: list[PageVisit] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)
    blocked_requests: int = 0


PageHook = Callable[[Page, PageVisit], Awaitable[None]]


async def _guard(route: Route, counter: list[int], allowed_origins: frozenset[str] | None) -> None:
    """Abort writes always; abort off-origin requests too when ``allowed_origins`` is set."""
    request = route.request
    off_origin = allowed_origins is not None and origin_of(request.url) not in allowed_origins
    if request.method.upper() in READ_ONLY_METHODS and not off_origin:
        await route.continue_()
    else:
        counter[0] += 1
        await route.abort("blockedbyclient")


async def new_readonly_context(
    browser: Browser,
    user_agent: str,
    viewport: tuple[int, int],
    counter: list[int],
    allowed_origins: frozenset[str] | None = None,
) -> BrowserContext:
    """A browser context that can only read. ``allowed_origins`` additionally makes it offline
    except for those origins (used by evals for determinism)."""
    context = await browser.new_context(
        user_agent=user_agent,
        viewport={"width": viewport[0], "height": viewport[1]},
        accept_downloads=False,
        service_workers="block",
        reduced_motion="reduce",
    )

    async def handler(route: Route) -> None:
        await _guard(route, counter, allowed_origins)

    await context.route("**/*", handler)
    return context


async def _links(page: Page) -> list[str]:
    hrefs: list[str] = await page.eval_on_selector_all(
        "a[href]", "els => els.map(e => e.getAttribute('href'))"
    )
    return [h for h in hrefs if h]


def _slug(index: int) -> str:
    return f"page-{index:03d}"


async def crawl(
    browser: Browser,
    config: CrawlConfig,
    out_dir: Path,
    on_page: PageHook | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> CrawlResult:
    """Breadth-first crawl from ``config.start_url``; call ``on_page`` while each page is open."""
    start = normalize(config.start_url)
    if start is None:
        raise ValueError(f"not an http(s) URL: {config.start_url}")

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pages").mkdir(exist_ok=True)

    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=10.0)
    try:
        robots = await RobotsPolicy.fetch(origin_of(start), config.user_agent, client)
    finally:
        if owns_client:
            await client.aclose()

    interval = max(config.min_interval, robots.crawl_delay or 0.0, 1.0)
    limiter = RateLimiter(min_interval=interval)
    result = CrawlResult()
    blocked = [0]
    allowed = frozenset({origin_of(start)}) if config.offline else None
    context = await new_readonly_context(
        browser, config.user_agent, config.viewport, blocked, allowed_origins=allowed
    )

    queue: deque[tuple[str, int]] = deque([(start, 0)])
    seen: set[str] = {start}
    try:
        while queue and len(result.visits) < config.max_pages:
            url, depth = queue.popleft()
            if not robots.allowed(url):
                result.skipped[url] = "disallowed by robots.txt"
                continue
            await limiter.wait(url)
            visit = PageVisit(url=url, final_url=url, depth=depth)
            page = await context.new_page()
            try:
                response = await page.goto(url, wait_until="load", timeout=NAV_TIMEOUT_MS)
                visit.status = response.status if response else None
                visit.final_url = normalize(page.url) or page.url
                content_type = response.headers.get("content-type", "") if response else ""
                if response is not None and "html" not in content_type:
                    result.skipped[url] = f"not HTML ({content_type or 'unknown'})"
                    continue
                visit.title = await page.title()
                slug = _slug(len(result.visits))
                shot = out_dir / "pages" / f"{slug}.png"
                dom = out_dir / "pages" / f"{slug}.html"
                await page.screenshot(path=str(shot), full_page=True)
                dom.write_text(await page.content(), encoding="utf-8")
                visit.screenshot = str(shot.relative_to(out_dir))
                visit.dom_snapshot = str(dom.relative_to(out_dir))
                if on_page is not None:
                    await on_page(page, visit)
                if depth < config.max_depth:
                    for href in await _links(page):
                        link = normalize(href, base=visit.final_url)
                        if link and link not in seen and same_origin(link, start):
                            seen.add(link)
                            queue.append((link, depth + 1))
            except Exception as exc:  # one broken page must not end the audit
                log.warning("failed to audit %s: %s", url, exc)
                visit.error = f"{type(exc).__name__}: {exc}"[:500]
            finally:
                await page.close()
            result.visits.append(visit)
        for url, _depth in queue:
            result.skipped.setdefault(url, "page cap reached")
    finally:
        result.blocked_requests = blocked[0]
        await context.close()
    return result
