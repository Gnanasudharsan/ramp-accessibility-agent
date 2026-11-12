# Ramp — Agentic Accessibility Auditor

**Finds accessibility barriers on any website, writes the fix, and proves it works.**

Ramp crawls a site in a sandboxed browser, runs deterministic WCAG checks with
[axe-core](https://github.com/dequelabs/axe-core), adds vision-model checks for the issues rule
engines miss (meaningless alt text, unclear link purpose, text baked into images, focus visibility),
generates minimal code patches, re-runs the checks to verify each patch, and opens a GitHub pull
request **only after a human approves the exact diff**.

Target standard: **WCAG 2.1 Level AA** (the standard adopted for US state and local government sites
under ADA Title II), with WCAG 2.2 criteria reported as an extra layer.

> Ramp never claims a site is "compliant". Automated tools catch only part of WCAG issues. Every
> report states what was checked, what was not, and recommends manual testing with assistive
> technology.

## Status

| Phase | Scope | Status |
|---|---|---|
| 0 | Foundation: layout, Compose stack, CI | ✅ done |
| 1 | Deterministic baseline: crawler, `ramp-a11y-mcp`, reports | ⏳ next |
| 2 | Benchmark and eval harness | — |
| 3 | LangGraph agent | — |
| 4 | Security and GitHub integration | — |
| 5 | Distilled vision model | — |
| 6 | LLMOps: tracing, eval-gated CI, registry | — |
| 7 | Web app, demo, v1.0.0 | — |

Results tables (baseline vs agent vs distilled model) will appear here as each phase produces them.
Every number in this README is produced by code in this repository.

## Quick start

```bash
make setup     # uv sync + pre-commit hooks
make test      # unit tests
make up        # api, worker, redis, MLflow, self-hosted Langfuse (Docker)
```

## Repository layout

```
ramp/
  agent/       LangGraph audit graph
  tools/       MCP client wrappers (Playwright MCP, GitHub MCP, ramp-a11y-mcp)
  mcp_server/  ramp-a11y-mcp: axe-core, contrast, focus order, DOM-to-source mapping
  crawler/     polite, read-only, same-origin crawler
  checks/      rule-engine and vision checks
  fixes/       patch generation and verification
  models/      LiteLLM providers, local VLM, distilled model, router
  evals/       benchmark loaders, metrics, runners
  api/         FastAPI + arq worker + SSE
web/           Next.js UI (static export on GitHub Pages)
training/      distillation data and MLX LoRA scripts
benchmark/     ground-truth pages and labels
infra/         Dockerfiles and Compose
docs/adr/      architecture decision records
```

## License

MIT © Gnanasudharsan Ashokumar
