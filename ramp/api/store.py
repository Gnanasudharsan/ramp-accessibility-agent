"""Audit jobs in Redis: a hash per audit (status, target, report) and a stream of events.

A Redis Stream (not pub/sub) carries progress events, so a client that connects late, or
reconnects with ``Last-Event-ID``, still receives every event in order. Everything expires after
``TTL_S``; the demo keeps no long-term record of what anyone audited.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel
from redis.asyncio import Redis

TTL_S = 24 * 3600
Status = Literal["queued", "running", "done", "failed"]
TERMINAL = {"done", "failed"}


class AuditJob(BaseModel):
    id: str
    url: str
    max_pages: int
    status: Status = "queued"
    created_at: str
    error: str | None = None
    summary: dict[str, Any] | None = None


class AuditStore:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    @staticmethod
    def _key(audit_id: str) -> str:
        return f"ramp:audit:{audit_id}"

    @staticmethod
    def _events(audit_id: str) -> str:
        return f"ramp:audit:{audit_id}:events"

    async def create(self, url: str, max_pages: int) -> AuditJob:
        job = AuditJob(
            id=secrets.token_urlsafe(12),
            url=url,
            max_pages=max_pages,
            created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        await self.redis.set(self._key(job.id), job.model_dump_json(), ex=TTL_S)
        await self.emit(job.id, "queued", {"url": url})
        return job

    async def get(self, audit_id: str) -> AuditJob | None:
        raw = await self.redis.get(self._key(audit_id))
        return AuditJob.model_validate_json(raw) if raw else None

    async def update(self, audit_id: str, **changes: Any) -> AuditJob:
        job = await self.get(audit_id)
        if job is None:
            raise KeyError(audit_id)
        job = job.model_copy(update=changes)
        await self.redis.set(self._key(audit_id), job.model_dump_json(), ex=TTL_S)
        return job

    async def save_report(self, audit_id: str, report_json: str) -> None:
        await self.redis.set(f"{self._key(audit_id)}:report", report_json, ex=TTL_S)

    async def report(self, audit_id: str) -> str | None:
        raw = await self.redis.get(f"{self._key(audit_id)}:report")
        return raw.decode() if isinstance(raw, bytes) else raw

    async def emit(self, audit_id: str, kind: str, data: dict[str, Any]) -> None:
        key = self._events(audit_id)
        await self.redis.xadd(key, {"kind": kind, "data": json.dumps(data)}, maxlen=500)
        await self.redis.expire(key, TTL_S)

    async def events(
        self, audit_id: str, after: str = "0-0", block_ms: int = 15_000
    ) -> AsyncIterator[tuple[str, str, dict[str, Any]]]:
        """Yield (event id, kind, data) from ``after`` until a terminal event."""
        last = after
        while True:
            batch = await self.redis.xread({self._events(audit_id): last}, block=block_ms)
            if not batch:
                job = await self.get(audit_id)
                if job is None or job.status in TERMINAL:
                    return
                yield "", "keepalive", {}
                continue
            for _stream, entries in batch:
                for entry_id, fields in entries:
                    last = _s(entry_id)
                    kind = _s(fields.get(b"kind", fields.get("kind", "")))
                    data = json.loads(_s(fields.get(b"data", fields.get("data", "{}"))))
                    yield last, kind, data
                    if kind in TERMINAL:
                        return

    async def allow(self, client: str, limit: int, window_s: int = 3600) -> bool:
        """Fixed-window rate limit per client (the demo protects a shared, free backend)."""
        key = f"ramp:rate:{client}"
        count = await self.redis.incr(key)
        if count == 1:
            await self.redis.expire(key, window_s)
        return int(count) <= limit


def _s(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)
