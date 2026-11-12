import httpx
import pytest

from ramp.crawler.politeness import RateLimiter, RobotsPolicy
from ramp.crawler.urls import normalize, same_origin

UA = "RampA11yBot/0.1"


def test_robots_wildcards_are_honoured() -> None:
    policy = RobotsPolicy.from_text(
        "User-agent: *\nDisallow: /*/wp-admin/\nDisallow: /*.pdf$\n", UA
    )
    assert not policy.allowed("https://x.org/blog/wp-admin/edit")
    assert not policy.allowed("https://x.org/files/report.pdf")
    assert policy.allowed("https://x.org/files/report.pdf.html")
    assert policy.allowed("https://x.org/about")


def test_robots_crawl_delay() -> None:
    policy = RobotsPolicy.from_text("User-agent: *\nCrawl-delay: 5\n", UA)
    assert policy.crawl_delay == 5.0


@pytest.mark.parametrize(
    ("status", "allowed"),
    [(404, True), (403, True), (500, False), (503, False)],
)
async def test_robots_status_handling_follows_rfc_9309(status: int, allowed: bool) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(status))
    async with httpx.AsyncClient(transport=transport) as client:
        policy = await RobotsPolicy.fetch("https://x.org", UA, client)
    assert policy.allowed("https://x.org/page") is allowed


async def test_robots_network_error_means_disallow() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    async with httpx.AsyncClient(transport=httpx.MockTransport(boom)) as client:
        policy = await RobotsPolicy.fetch("https://x.org", UA, client)
    assert not policy.allowed("https://x.org/")


async def test_rate_limiter_spaces_requests_per_host() -> None:
    now = [100.0]

    def sleep(seconds: float) -> None:
        now[0] += seconds

    limiter = RateLimiter(min_interval=1.0, clock=lambda: now[0], sleep=sleep)
    assert await limiter.wait("https://a.org/1") == 0.0
    assert await limiter.wait("https://a.org/2") == pytest.approx(1.0)
    assert await limiter.wait("https://b.org/1") == 0.0  # other host: no wait
    now[0] += 5
    assert await limiter.wait("https://a.org/3") == 0.0


def test_normalize() -> None:
    assert normalize("page.html#x", base="https://A.org/dir/") == "https://a.org/dir/page.html"
    assert normalize("mailto:a@b.c") is None
    assert normalize("javascript:void(0)") is None
    assert normalize("/files/doc.PDF", base="https://a.org") is None
    assert normalize("https://a.org") == "https://a.org/"
    assert normalize("?q=1", base="https://a.org/s") == "https://a.org/s?q=1"


def test_same_origin() -> None:
    assert same_origin("https://a.org/x", "https://A.org/y")
    assert not same_origin("https://a.org/x", "http://a.org/x")
    assert not same_origin("https://a.org/x", "https://b.a.org/x")
