# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); phases are tagged `phase-N`.

## [Unreleased]

## [phase-0] — 2026-11-12 — Foundation
### Added
- Repository layout (`ramp/{agent,tools,mcp_server,crawler,checks,fixes,models,evals,api}`,
  `web/`, `training/`, `benchmark/`, `infra/`, `docs/`, `tests/`).
- Python 3.12 + uv project, typed settings with enforced crawl etiquette (≥ 1 s between requests).
- FastAPI app with `/healthz`, arq worker, `ramp` CLI skeleton.
- Docker Compose stack: api, worker, redis, MLflow, self-hosted Langfuse (web, worker,
  Postgres, ClickHouse, MinIO).
- Makefile (`make up`, `test`, `lint`, `eval`, `audit URL=...`), pre-commit, GitHub Actions CI
  (ruff, mypy strict, pytest).
- CLAUDE.md working agreement, ADR 0001–0002, MIT license.
