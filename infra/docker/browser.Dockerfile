# Sandboxed browser: runs ramp-a11y-mcp (Playwright + Chromium) and nothing else.
# Hardening lives in docker-compose.yml (read-only rootfs, no capabilities, resource limits,
# network isolation from internal services). The image itself runs as an unprivileged user
# and contains no secrets.
FROM mcr.microsoft.com/playwright/python:v1.65.0-noble
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright HOME=/tmp
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY ramp ./ramp
RUN uv sync --frozen --no-dev && useradd --create-home --uid 10002 browser
USER browser
ENV PATH="/app/.venv/bin:${PATH}" RAMP_MCP_TRANSPORT=streamable-http RAMP_MCP_PORT=8765
EXPOSE 8765
CMD ["ramp", "mcp-server"]
