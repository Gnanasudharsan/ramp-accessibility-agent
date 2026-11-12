"""Download the W3C "Before and After Demonstration" (BAD) pages for offline, reproducible evals.

Source: https://www.w3.org/WAI/demos/bad/ — Copyright W3C (MIT, ERCIM, Keio, Beihang), used
under the W3C Document License. Files are saved unmodified under ``benchmark/bad/site/`` (which
is gitignored) with their original paths, so relative links keep working when served locally.

The fetch is polite: robots.txt is checked, one page navigation per second, Ramp's User-Agent,
and only GET requests. Page requisites (CSS, images, scripts) are captured from the browser's
own responses, restricted to the ``/WAI/demos/bad/`` prefix.

Usage: ``uv run python benchmark/bad/fetch_bad.py``
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from playwright.async_api import Response

from ramp.audit import launch_browser
from ramp.config import get_settings
from ramp.crawler.crawler import new_readonly_context
from ramp.crawler.politeness import RateLimiter, RobotsPolicy

BASE = "https://www.w3.org/WAI/demos/bad/"
PAGES = ["home.html", "news.html", "tickets.html", "survey.html"]
VARIANTS = ["before", "after"]
OUT = Path(__file__).parent / "site"


async def main() -> None:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=15) as client:
        robots = await RobotsPolicy.fetch("https://www.w3.org", settings.user_agent, client)
    limiter = RateLimiter(min_interval=max(1.0, robots.crawl_delay or 0.0))
    saved: dict[str, str] = {}

    async with launch_browser() as browser:
        context = await new_readonly_context(browser, settings.user_agent, (1280, 900), [0])

        async def on_response(response: Response) -> None:
            if not response.url.startswith(BASE) or response.status != 200:
                return
            path = urlsplit(response.url).path.lstrip("/")
            try:
                body = await response.body()
            except Exception:
                return
            dest = OUT / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(body)
            saved[path] = hashlib.sha256(body).hexdigest()

        context.on("response", on_response)
        page = await context.new_page()
        for variant in VARIANTS:
            for name in PAGES:
                url = f"{BASE}{variant}/{name}"
                if not robots.allowed(url):
                    raise SystemExit(f"robots.txt disallows {url}")
                await limiter.wait(url)
                await page.goto(url, wait_until="networkidle")
                print(f"fetched {url}")
        await context.close()

    manifest = OUT / "MANIFEST.json"
    manifest.write_text(
        json.dumps({"source": BASE, "files": dict(sorted(saved.items()))}, indent=2)
    )
    print(f"saved {len(saved)} files under {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
