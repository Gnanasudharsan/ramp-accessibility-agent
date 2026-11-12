"""FastAPI application. Phase 0 exposes health and version; audit endpoints arrive in Phase 7."""

from __future__ import annotations

from fastapi import FastAPI

from ramp import __version__

app = FastAPI(title="Ramp", version=__version__)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe used by Docker Compose and the demo host."""
    return {"status": "ok", "version": __version__}
