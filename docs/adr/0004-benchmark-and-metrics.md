# ADR 0004 — Benchmark design and metrics

- Status: accepted
- Date: 2026-11-12

## Context
Phase 3 adds model-based checks. Without a benchmark that existed first, any improvement claim
would be anecdotal, and precision regressions (hallucinated issues) would go unseen.

## Decisions
1. **Three sets, three questions.** Synthetic pages (element level) measure what each check finds;
   W3C BAD (page × criterion) measures agreement with an external authority; adversarial pages
   measure whether page content can steer the system.
2. **Match on element + criterion overlap**, resolving every selector to a canonical element in the
   live DOM. Label and prediction selectors rarely match as strings; elements do.
3. **Duplicates are not false positives.** The agent will merge rule and vision findings; a second
   finding on an already-matched label is reported as a duplicate so dedupe quality is visible
   without distorting precision.
4. **Best-practice findings are not scored.** They carry no WCAG criterion.
5. **BAD is scored twice**: against W3C annotations only, and with labeler-verified additions, so
   the reader can see how much a labeling decision moves the number.
6. **Canary checks use generated text only.** Evidence is quoted page content by design; the test
   is whether the system *repeats an instruction as its own output*.
7. **Smoke subset** (flagged `smoke: true`: 4 synthetic, 2 adversarial, 2 BAD pages) runs in CI on
   every push; the full set runs with `make eval`.
8. **Baseline = axe-core only**, results committed in `evals/results/axe-baseline/`.

## Consequences
- The synthetic set is small (37 pages, 37 labels) and written by one person; per-criterion numbers
  with fewer than ~5 labels are reported but should not be over-read.
- On synthetic pages the baseline's precision is 1.0 partly by construction (labels are validated
  against axe). Precision is the metric to watch for model-based checks, not for axe.
