"""Langfuse tracing (Phase 6): one trace per audit, one generation per model call.

Tracing is off unless ``LANGFUSE_PUBLIC_KEY`` and ``LANGFUSE_SECRET_KEY`` are set (``.env``;
Docker Compose provisions a matching local project). It never changes behaviour: if Langfuse is
down, spans are dropped. Image parts are replaced by a size placeholder and long strings are
truncated in Ramp's code, before the SDK sees them (the SDK would otherwise upload base64 images
to its media store). Page text is still sent, so point it only at a self-hosted instance
(Compose keeps it on the internal network).
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from functools import lru_cache
from typing import Any

MAX_CHARS = 4000


@lru_cache(maxsize=1)
def tracer() -> Any | None:
    """The Langfuse client, or None when tracing is not configured."""
    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        return None
    from langfuse import Langfuse

    return Langfuse(
        base_url=os.environ.get("LANGFUSE_HOST", "http://localhost:3001"),
        environment=os.environ.get("RAMP_ENV", "development"),
        mask=_mask,
    )


def _mask(*, data: Any, **_: Any) -> Any:
    return redact(data)


def redact(value: Any) -> Any:
    """Replace base64 images with a placeholder and truncate long strings, recursively."""
    if isinstance(value, dict):
        if value.get("type") == "image_url":
            url = str((value.get("image_url") or {}).get("url", ""))
            return {"type": "image", "bytes_base64": len(url)}
        return {k: redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        if value.startswith("data:image"):
            return f"[image, {len(value)} base64 chars]"
        return value if len(value) <= MAX_CHARS else value[:MAX_CHARS] + "…[truncated]"
    return value


def prompt_hash(system: str) -> str:
    """Short hash of the system prompt, so traces group by prompt version."""
    return hashlib.sha256(system.encode()).hexdigest()[:8]


@contextmanager
def audit_trace(name: str, **metadata: Any) -> Iterator[None]:
    """Wrap one audit (or one eval page) so its model calls nest under a single trace."""
    client = tracer()
    if client is None:
        yield
        return
    with client.start_as_current_observation(name=name, as_type="agent", metadata=metadata):
        yield
    client.flush()


def generation(name: str, model: str, messages: list[dict[str, Any]], **metadata: Any) -> Any:
    """Context manager for one model call; ``.update(...)`` it with output and usage."""
    client = tracer()
    if client is None:
        return nullcontext(_NoSpan())
    # Redact here, before the SDK sees the data: the SDK uploads base64 media to its own store
    # before any ``mask`` callback runs, so masking alone would still ship screenshots.
    return client.start_as_current_observation(
        name=name, as_type="generation", model=model, input=redact(messages), metadata=metadata
    )


class _NoSpan:
    def update(self, **_: Any) -> None:
        return None
