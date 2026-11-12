# ADR 0002 — Foundation stack and local infrastructure

- Status: accepted
- Date: 2026-11-12

## Context
Budget is $0 and development happens on a 16 GB Apple Silicon Mac. The stack must run locally,
in free CI, and on free hosting.

## Decision
- **Python 3.12 + uv** with a committed `uv.lock` for reproducible installs. Dependencies are added
  in the phase that first needs them, so each phase's lockfile diff is reviewable.
- **One Redis** serves both the arq job queue (`db 1`) and Langfuse (`db 0`). Fewer containers,
  same isolation in practice; Langfuse requires `noeviction`, which is also correct for a job queue.
- **Langfuse v4 self-hosted** follows the upstream Compose topology (web, worker, Postgres,
  ClickHouse, MinIO) trimmed to the variables we use. It sits behind the `observability` Compose
  profile: `make up` starts everything, `make up-core` skips the ~2 GB observability stack.
- **MLflow** runs as a single container with a SQLite backend and local artifact volume.
- **Host ports** avoid macOS conflicts: API 8088 (override with `RAMP_API_PORT`), Langfuse 3001 (Next.js dev owns 3000),
  MLflow 5001 (AirPlay owns 5000). Data stores bind to 127.0.0.1 only.
- **Web UI** ships as a static Next.js export on GitHub Pages (free, served from the author's GitHub
  profile) instead of Vercel; live audits call the demo API on Hugging Face Spaces.

## Consequences
- `make up` needs Docker Desktop with ~4 GB RAM available for the full stack.
- A static web build means no server-side rendering; all dynamic behaviour goes through the API.
