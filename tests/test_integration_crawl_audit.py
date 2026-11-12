"""Browser-backed tests against the local fixture site (``make test-all``)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from ramp.audit import audit_url, launch_browser
from ramp.crawler.crawler import CrawlConfig, crawl
from tests.conftest import StaticServer

pytestmark = pytest.mark.integration
UA = "RampA11yBot/test"


async def test_crawler_is_polite_read_only_and_same_origin(
    fixture_site: StaticServer, tmp_path: Path
) -> None:
    config = CrawlConfig(start_url=f"{fixture_site.url}/index.html", user_agent=UA, max_pages=10)
    started = time.monotonic()
    async with launch_browser() as browser:
        result = await crawl(browser, config, tmp_path)
    elapsed = time.monotonic() - started

    visited = [v.url.removeprefix(fixture_site.url) for v in result.visits]
    assert visited == ["/index.html", "/page2.html", "/page3.html"]
    assert result.skipped[f"{fixture_site.url}/private/secret.html"] == "disallowed by robots.txt"
    assert not any("example.org" in url for url in result.skipped)  # never even queued
    # Read-only: the form was never submitted and the page's POST beacon was blocked.
    assert ("POST", "/beacon") not in fixture_site.requests
    assert result.blocked_requests >= 1
    assert all(method == "GET" for method, _ in fixture_site.requests)
    # Rate limit: three page navigations need at least two full intervals.
    assert elapsed >= 2.0
    for visit in result.visits:
        assert visit.screenshot
        assert (tmp_path / visit.screenshot).exists()
        assert visit.dom_snapshot
        assert (tmp_path / visit.dom_snapshot).exists()


async def test_crawler_page_cap(fixture_site: StaticServer, tmp_path: Path) -> None:
    config = CrawlConfig(start_url=f"{fixture_site.url}/index.html", user_agent=UA, max_pages=1)
    async with launch_browser() as browser:
        result = await crawl(browser, config, tmp_path)
    assert len(result.visits) == 1
    assert result.skipped[f"{fixture_site.url}/page2.html"] == "page cap reached"


async def test_same_content_at_two_urls_is_audited_once(
    fixture_site: StaticServer, tmp_path: Path
) -> None:
    """ "/" and "/index.html" serve the same page; auditing both would duplicate every finding."""
    config = CrawlConfig(start_url=f"{fixture_site.url}/", user_agent=UA, max_pages=10, max_depth=3)
    async with launch_browser() as browser:
        result = await crawl(browser, config, tmp_path)
    visited = [v.url.removeprefix(fixture_site.url) for v in result.visits]
    assert visited == ["/", "/page2.html", "/page3.html"]
    home = f"{fixture_site.url}/"
    assert result.skipped[f"{home}index.html"] == f"same content as {home}"


async def test_audit_finds_rule_issues_with_evidence(
    fixture_site: StaticServer, tmp_path: Path
) -> None:
    report = await audit_url(
        f"{fixture_site.url}/index.html", tmp_path, user_agent=UA, max_pages=1, max_depth=0
    )
    rules = {i.rule_id for i in report.issues}
    assert {"image-alt", "color-contrast"} <= rules
    image = next(i for i in report.issues if i.rule_id == "image-alt")
    assert image.selector == "#hero"
    assert image.criteria == ["1.1.1"]
    assert image.evidence.screenshot_crop is not None
    assert (tmp_path / image.evidence.screenshot_crop).exists()
    assert report.coverage.axe_version == "4.14.0"
    assert "1.4.3" in report.coverage.criteria_checked
    assert "1.3.3" in report.coverage.criteria_not_checked  # Sensory Characteristics: manual


async def test_private_network_is_refused_when_not_explicitly_allowed(
    fixture_site: StaticServer, tmp_path: Path
) -> None:
    """SSRF: with private targets disallowed, the browser cannot load a loopback address."""
    config = CrawlConfig(
        start_url=f"{fixture_site.url}/index.html", user_agent=UA, max_pages=1, allow_private=False
    )
    async with launch_browser() as browser:
        result = await crawl(browser, config, tmp_path)
    assert result.visits[0].error is not None
    assert fixture_site.requests == [("GET", "/robots.txt")]  # only the robots.txt fetch (httpx)
