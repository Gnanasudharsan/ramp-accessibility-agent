"""FastAPI application: submit an audit, follow its progress (SSE), read the report.

The request path never runs a browser. ``POST /api/audits`` validates the target (public
http(s) only, so the demo cannot be pointed at internal services), applies a per-client rate
limit, and enqueues an arq job; the worker crawls (robots.txt, one request per second, page cap)
and writes progress events and the report to Redis.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, Protocol

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field, HttpUrl
from redis.asyncio import Redis
from sse_starlette.sse import EventSourceResponse

from ramp import __version__
from ramp.api.store import AuditJob, AuditStore
from ramp.config import get_settings
from ramp.security.netpolicy import url_is_private


class Enqueue(Protocol):
    def __call__(self, audit_id: str, url: str, max_pages: int) -> Awaitable[None]: ...


class AuditRequest(BaseModel):
    url: HttpUrl
    max_pages: int = Field(default=3, ge=1)


class AuditCreated(BaseModel):
    id: str
    status: str
    status_url: str
    events_url: str


def create_app(
    redis: Redis | None = None,
    enqueue: Enqueue | None = None,
    is_private: Callable[[str], Awaitable[bool]] = url_is_private,
) -> FastAPI:
    """Build the app. Tests pass a fake Redis and enqueuer; production builds both from settings."""
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        pool = None
        if redis is None or enqueue is None:
            from arq import create_pool
            from arq.connections import RedisSettings

            pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        app.state.store = AuditStore(redis if redis is not None else pool)  # type: ignore[arg-type]

        async def arq_enqueue(audit_id: str, url: str, max_pages: int) -> None:
            assert pool is not None
            await pool.enqueue_job("run_audit", audit_id, url, max_pages, _job_id=audit_id)

        app.state.enqueue = enqueue or arq_enqueue
        try:
            yield
        finally:
            if pool is not None:
                await pool.aclose()

    app = FastAPI(title="Ramp", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api_cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Last-Event-ID"],
    )

    def store(request: Request) -> AuditStore:
        return request.app.state.store  # type: ignore[no-any-return]

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        """Liveness probe used by Docker Compose and the demo host."""
        return {"status": "ok", "version": __version__}

    @app.post("/api/audits", status_code=202)
    async def create_audit(body: AuditRequest, request: Request) -> AuditCreated:
        url = str(body.url)
        if body.max_pages > settings.api_max_pages:
            raise HTTPException(422, f"max_pages is limited to {settings.api_max_pages}")
        if await is_private(url):
            raise HTTPException(422, "only public http(s) addresses can be audited")
        client = request.client.host if request.client else "unknown"
        if not await store(request).allow(client, settings.api_audits_per_hour):
            raise HTTPException(429, "audit limit reached for this hour; try again later")
        job = await store(request).create(url, body.max_pages)
        await request.app.state.enqueue(job.id, url, body.max_pages)
        return AuditCreated(
            id=job.id,
            status=job.status,
            status_url=f"/api/audits/{job.id}",
            events_url=f"/api/audits/{job.id}/events",
        )

    @app.get("/api/audits/{audit_id}")
    async def get_audit(audit_id: str, request: Request) -> AuditJob:
        job = await store(request).get(audit_id)
        if job is None:
            raise HTTPException(404, "unknown or expired audit")
        return job

    @app.get("/api/audits/{audit_id}/report")
    async def get_report(audit_id: str, request: Request) -> Response:
        report = await store(request).report(audit_id)
        if report is None:
            raise HTTPException(404, "report not ready, unknown, or expired")
        return Response(report, media_type="application/json")

    @app.get("/api/audits/{audit_id}/events")
    async def audit_events(audit_id: str, request: Request) -> EventSourceResponse:
        if await store(request).get(audit_id) is None:
            raise HTTPException(404, "unknown or expired audit")
        after = request.headers.get("last-event-id") or "0-0"

        async def stream() -> AsyncIterator[dict[str, Any]]:
            async for event_id, kind, data in store(request).events(audit_id, after):
                if kind == "keepalive":
                    yield {"comment": "keepalive"}
                    continue
                yield {"id": event_id, "event": kind, "data": json.dumps(data)}

        return EventSourceResponse(stream())

    return app


app = create_app()
