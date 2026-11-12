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
| 2 | Benchmark and eval harness | ✅ done |
| 3 | LangGraph agent | ⏳ next |
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

Counts are from macOS; on CI's Ubuntu runner both tools find 318 (one more `color-contrast`
node on `before/tickets`, a font-rendering difference) and still match exactly. The "after"
pages still trigger 79 axe findings — all best-practice rules or WCAG 2.2's 2.5.8 Target Size,
which postdates the demo — so even expert-repaired pages are not "zero findings".

### Phase 2 — benchmark and the axe-core baseline

The benchmark ([`benchmark/`](benchmark/), [labeling guidelines](docs/labeling-guidelines.md))
was built before any model-based check. Baseline = axe-core 4.14 only
([`evals/results/axe-baseline/full.md`](evals/results/axe-baseline/full.md)):

| Benchmark | Precision | Recall | F1 |
|---|---:|---:|---:|
| Synthetic, all 37 labels (37 pages) | 1.000 | 0.432 | 0.604 |
| Synthetic, 16 rule-detectable labels | 1.000 | 1.000 | 1.000 |
| Synthetic, 21 labels that need judgment (alt quality, link purpose, images of text, focus, captions) | — | **0.000** | — |
| W3C BAD, page × WCAG 2.0 criterion, W3C annotations only | 0.611 | 0.212 | 0.314 |
| W3C BAD, W3C + labeler-verified failures | 1.000 | 0.305 | 0.468 |

Prompt-injection resistance: 10/10 adversarial pages — trivially, since the baseline calls no
model. Latency p50 0.28 s per page; cost $0. The 0.000 recall on judgment-based labels is the gap
the agent in Phase 3 has to close without giving up precision.

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
