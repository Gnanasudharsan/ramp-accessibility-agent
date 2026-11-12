"""arq background worker. Long-running audits run here, not in the request path."""

from __future__ import annotations

from typing import Any, ClassVar

from arq.connections import RedisSettings

from ramp.config import get_settings


async def ping(ctx: dict[str, Any]) -> str:
    """Trivial job used to verify the queue end to end."""
    return "pong"


class WorkerSettings:
    """arq discovers this class by import path: ``arq ramp.api.worker.WorkerSettings``."""

    functions: ClassVar[list[Any]] = [ping]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
