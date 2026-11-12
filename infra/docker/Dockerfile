# Image for the Ramp API and worker. Multi-stage: dependencies are resolved by uv from uv.lock.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv
WORKDIR /app
# Playwright's Node driver (used to *connect* to the sandboxed browser; no browser is installed
# here) needs libatomic.
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 \
    && rm -rf /var/lib/apt/lists/*

FROM base AS deps
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

FROM deps AS runtime
COPY ramp ./ramp
RUN uv sync --frozen --no-dev && useradd --create-home --uid 10001 ramp
USER ramp
ENV PATH="/app/.venv/bin:${PATH}"
EXPOSE 8000
CMD ["uvicorn", "ramp.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
