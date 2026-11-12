"""arq background worker. Audits run here, not in the request path.

One Chromium instance is started per worker process and shared by jobs; each job gets its own
read-only browser context from the crawler, so jobs do not share cookies or storage.
"""

from __future__ import annotations

import tempfile
from collections import Counter
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, ClassVar

from arq.connections import RedisSettings

from ramp.api.store import AuditStore
from ramp.audit import audit_url, launch_browser
from ramp.config import get_settings
from ramp.crawler.politeness import SharedRateLimiter
from ramp.report.schema import AuditReport, PageResult


async def ping(ctx: dict[str, Any]) -> str:
    """Trivial job used to verify the queue end to end."""
    return "pong"


def summarize(report: AuditReport) -> dict[str, Any]:
    """Small summary for the status endpoint and the final event (the full report is separate)."""
    issues = report.issues
    return {
        "pages_audited": sum(1 for p in report.pages if p.status == 200),
        "issues": len(issues),
        "by_severity": dict(Counter(str(i.severity) for i in issues)),
        "criteria_failing": sorted({c for i in issues for c in i.criteria}),
        "criteria_checked": len(report.coverage.criteria_checked),
        "criteria_not_checked": len(report.coverage.criteria_not_checked),
        "skipped_urls": len(report.skipped_urls),
    }


async def run_audit(ctx: dict[str, Any], audit_id: str, url: str, max_pages: int) -> str:
    store: AuditStore = ctx["store"]
    settings = get_settings()
    await store.update(audit_id, status="running")
    await store.emit(audit_id, "running", {"url": url, "max_pages": max_pages})

    async def progress(page: PageResult) -> None:
        await store.emit(
            audit_id,
            "page",
            {"url": page.final_url, "title": page.title, "issues": len(page.issues)},
        )

    try:
        with tempfile.TemporaryDirectory() as tmp:
            report = await audit_url(
                url,
                Path(tmp),
                user_agent=settings.user_agent,
                max_pages=max_pages,
                max_depth=1,
                browser=ctx["browser"],
                on_progress=progress,
                # One request per second per site across all jobs and workers, not per job.
                limiter_factory=lambda interval: SharedRateLimiter(ctx["redis"], interval),
            )
        summary = summarize(report)
        await store.save_report(audit_id, report.model_dump_json())
        await store.update(audit_id, status="done", summary=summary)
        await store.emit(audit_id, "done", summary)
        return "done"
    except Exception as exc:  # report every failure to the client, then let arq record it
        message = f"{type(exc).__name__}: {str(exc)[:300]}"
        await store.update(audit_id, status="failed", error=message)
        await store.emit(audit_id, "failed", {"error": message})
        raise


async def startup(ctx: dict[str, Any]) -> None:
    stack = AsyncExitStack()
    ctx["stack"] = stack
    ctx["browser"] = await stack.enter_async_context(launch_browser())
    ctx["store"] = AuditStore(ctx["redis"])


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["stack"].aclose()


class WorkerSettings:
    """arq discovers this class by import path: ``arq ramp.api.worker.WorkerSettings``."""

    functions: ClassVar[list[Any]] = [ping, run_audit]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 2  # each job drives a browser; keep memory bounded on a small demo host
    job_timeout = 300
    max_tries = 1  # a failed crawl is reported, not silently retried against someone's site
