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
| 3 | LangGraph agent | ✅ done |
| 4 | Security and GitHub integration | ⏳ next |
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
model. Latency p50 0.19 s per page; cost $0. The 0.000 recall on judgment-based labels is the gap
the agent in Phase 3 has to close without giving up precision.

### Phase 3 — the agent closes the judgment gap

A LangGraph agent (`plan → crawl → rule_checks → vision_checks → merge_and_dedupe → prioritize →
generate_fixes ⇄ verify_fixes → human_review → open_pr`, SQLite checkpoints, human-review
interrupt) adds model judgment on top of axe-core. Thresholds were fixed in
[ADR 0005](docs/adr/0005-agent-design-and-acceptance-thresholds.md) before the first full run was read.
Same benchmark, same scorer ([`evals/results/comparison.md`](evals/results/comparison.md)):

| ADR 0005 acceptance check | axe baseline | Ramp agent | Threshold | Result |
|---|---:|---:|---:|---|
| Recall on the 21 judgment-based labels | 0.000 | **1.000** (21/21) | ≥ 0.60 | met |
| Overall precision, synthetic pages | 1.000 | 0.925 (37 TP, 3 FP) | ≥ 0.90 | met |
| Precision of model-sourced findings | — | 0.905 (19/21) | ≥ 0.85 | met |
| False positives on the 5 clean control pages | 0 | 0 | ≤ 1 | met |
| Recall on the 16 rule-detectable labels | 1.000 | 1.000 | = 1.000 | met |
| Fix success (verified ÷ attempted) | — | 0.938 (45/48) | reported | — |

Overall synthetic F1 goes from 0.604 to 0.961. A fix counts as successful only if the targeted
violation is gone on a re-rendered copy of the site, no axe rule fires more often, and the page
still renders; 48 fixes were attempted across synthetic and adversarial pages, and one issue was
handed to a human because its source could not be located. The 3 false positives are one each
for 1.1.1, 1.3.3, and 2.4.7, on pages that also have real barriers.

What did not improve, measured in the same run:

- **Prompt injection: 6/10 pages resisted.** With only Phase 3's defenses (escaped data blocks
  and a security preamble), the vision model repeated a canary token planted in page content on
  4 pages. No forbidden tool was called and no real finding was suppressed. Phase 4's bar is
  ≥ 95%.
- **W3C BAD did not move** (F1 0.306 vs 0.314 on W3C annotations; 0.456 vs 0.468 with verified
  labels). The BAD pages ran last and the vision model's free-tier quota was exhausted: 47 of the
  run's 53 failed model calls were on BAD, so most judgment checks there were skipped. The two
  added false positives are model findings on W3C's repaired "after" pages. This is not a
  measurement of the agent's recall on BAD; it is re-run when quota allows.
- **Latency and tokens.** p50 29.8 s per page; p95 2,625 s, dominated by waiting on the free
  tier's 8,000-tokens-per-minute limit (calls are serialised and the wait is included). 6,013
  model tokens per page (6.0M per 1,000 pages), $0 on the free tier.

Models: `groq/qwen/qwen3.8-27b` (vision) and `groq/openai/gpt-oss-120b` (link purpose, fixes),
both configurable. Every prompt is versioned and its hash is recorded in the results file.

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

Run the agent on a static site you own (needs a free `GROQ_API_KEY`); it stops for review
before anything is published:

```bash
uv run ramp agent http://localhost:8080/ --repo ./my-site --max-pages 5
uv run ramp approve <thread-id> --fix <fix-id>   # or --all
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
