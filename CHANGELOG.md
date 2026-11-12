# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); phases are tagged `phase-N`.

## [Unreleased]

## [phase-1] — 2026-11-12 — Deterministic baseline
### Added
- Polite, read-only, same-origin Playwright crawler: robots.txt (RFC 9309 via protego), ≤ 1 page
  navigation/s per host, depth and page caps, non-GET requests aborted, screenshot + DOM snapshot.
- Vendored axe-core 4.14.0 runner; lossless conversion to Ramp issues with WCAG 2.2 criteria map.
- Report schema v1.0 (issue, criterion, severity, selector, evidence crop, detection source,
  confidence, coverage of what was and was not checked) with JSON and accessible HTML output.
- `ramp audit <url>` CLI.
- `ramp-a11y-mcp` server (MCP SDK v2): `run_axe`, `contrast_check`, `focus_order`,
  `map_to_source`; tested in-process and over stdio.
- W3C BAD fetcher and reproduction check against `@axe-core/playwright`: 317/317 findings match.
- ADR 0003.

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
