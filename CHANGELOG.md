# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); phases are tagged `phase-N`.

## [Unreleased]

## [phase-3] — 2026-11-12 — The agent
### Added
- LangGraph audit graph with a Pydantic state, SQLite checkpoints (deserialiser restricted to
  Ramp's types), a fix ⇄ verify repair loop (two attempts, then "needs human"), and a
  human-review interrupt; `ramp agent` and `ramp approve`.
- Evidence collection (image crops, link context, heading-like text, tables, media, sensory
  instructions) and judgment checks through LiteLLM with schema-validated, cached calls;
  focus visibility (2.4.7) decided by a pixel diff.
- Fix generation as single exact-substring patches located with `map_to_source`, verified on a
  re-rendered copy of the site (violation gone, no new violations, page renders, pixel diff).
- Report schema 1.1 (element keys, suggested fixes, fix summaries, model usage).
- `ramp.evals.compare`; agent results in `evals/results/ramp-agent/`. ADR 0005 with thresholds
  agreed before the first full run.

### Measured
- Judgment-label recall 0.000 → 1.000; synthetic precision 0.925, F1 0.961; model-sourced
  precision 0.905; 0 control-page false positives; fix success 45/48. All ADR 0005 thresholds met.
- Not yet good enough: injection resistance 6/10; W3C BAD unchanged because the free-tier quota
  ran out during the BAD pages (47 of 53 failed calls).

### Fixed
- README baseline latency now matches the results file (p50 0.19 s).

## [phase-2] — 2026-11-12 — Benchmark and eval harness
### Added
- Versioned label schema v1.0 (Pydantic + committed JSON Schema) and labeling guidelines.
- 37 synthetic pages (16 rule-detectable, 16 judgment-based, 5 clean controls) and 10
  prompt-injection pages, generated with their labels from one spec file; drawn images.
- W3C BAD page × criterion labels from W3C's annotations, with labeler-verified additions kept
  separate.
- Metrics: element matching on canonical DOM elements, P/R/F1 per criterion, per detectable-by,
  per detection source; BAD page-criterion scores; injection resistance (canary, forbidden tools,
  suppression); latency p50/p95; cost per 1,000 pages; fix success rate.
- `make eval` / `make eval-smoke`; CI runs the smoke subset and uploads results.
- Label quality gate test; baseline results in `evals/results/axe-baseline/`. ADR 0004.

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
