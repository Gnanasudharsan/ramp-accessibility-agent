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
| 1 | Deterministic baseline: crawler, `ramp-a11y-mcp`, reports | ✅ done |
| 2 | Benchmark and eval harness | ⏳ next |
| 3 | LangGraph agent | — |
| 4 | Security and GitHub integration | — |
| 5 | Distilled vision model | — |
| 6 | LLMOps: tracing, eval-gated CI, registry | — |
| 7 | Web app, demo, v1.0.0 | — |

Every number in this README is produced by code in this repository.

### Phase 1 — the deterministic baseline reproduces axe-core exactly

Ramp's pipeline (crawler → injected axe-core → report) against Deque's official
`@axe-core/playwright`, same axe-core 4.14.0 and tags, on the eight
[W3C BAD](https://www.w3.org/WAI/demos/bad/) pages served offline
([`evals/results/bad_reproduction.md`](evals/results/bad_reproduction.md), checked in CI):

| Page set | Reference findings | Ramp findings | Exact match |
|---|---:|---:|---|
| BAD "before" (4 inaccessible pages) | 238 | 238 | yes |
| BAD "after" (4 repaired pages) | 79 | 79 | yes |

The "after" pages still trigger 79 axe findings, so a page that experts repaired is not
"zero findings" — one reason Ramp never reports a site as compliant.

## Quick start

```bash
make setup     # uv sync + pre-commit hooks
make test      # unit tests
make up        # api, worker, redis, MLflow, self-hosted Langfuse (Docker)
```

Audit a site and use the MCP server:

```bash
uv run ramp audit https://www.w3.org/WAI/demos/bad/before/home.html --max-pages 1
uv run ramp mcp-server    # stdio; tools: run_axe, contrast_check, focus_order, map_to_source
```

MCP client config (Claude Desktop, Cursor, or any MCP client):

```json
{ "mcpServers": { "ramp-a11y": { "command": "uv", "args": ["run", "--directory", "/path/to/ramp-accessibility-agent", "ramp", "mcp-server"] } } }
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
