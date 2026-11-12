# ADR 0005 — Agent design, models, and Phase 3 acceptance thresholds

- Status: accepted
- Date: 2026-11-12 (thresholds fixed before the first full agent eval was read)

## Context
Phase 3 adds model judgment to a deterministic baseline that has precision 1.000 but recall
0.000 on the 21 benchmark labels that need judgment (ADR 0004). Models can hallucinate issues,
and page content can try to steer them. We need a design that adds recall without giving up the
trust that comes from precision, and a bar agreed in advance.

## Decisions

**Graph.** LangGraph `plan → crawl → rule_checks → vision_checks → merge_and_dedupe → prioritize →
generate_fixes ⇄ verify_fixes → human_review → open_pr`. State is a Pydantic model holding only
serialisable data (images are files), checkpointed to SQLite so audits resume after a crash and
after the review interrupt. The checkpoint deserialiser is restricted to Ramp's own state types.

**Collect, then judge.** `crawl` gathers candidates (images with crops, links with programmatic
context, heading-like text, header-less tables, media, sensory instructions, color-styled form
labels). Models only judge candidates; they never browse.

**Deterministic where possible.** Focus visibility (2.4.7) is a pixel diff of each focus stop,
focused vs unfocused — more reliable than asking a model whether two crops differ. Severity and
WCAG criterion come from fixed tables keyed by finding type, never from model output.

**Output validation.** Every model reply must parse into a Pydantic schema (retry with the error,
max 2), may only reference candidate ids we sent, must name a criterion allowed for that
candidate kind, and must clear a confidence floor (0.6) to become an issue.

**Untrusted content.** Page data goes in JSON blocks with `<` and `>` escaped (it cannot close its
delimiter); source code goes in raw blocks closed by a random per-call boundary. A shared
security preamble tells models that page and image text is data. Per-node tool allowlists are
recorded and checked (`NODE_TOOLS`). Phase 4 adds canary scrubbing and a red-team gate.

**Fixes.** One exact-substring replacement per fix, in the file `map_to_source` ranks highest
(the file served at the audited URL wins ties). A fix is *successful* only if the targeted
violation is gone (axe: same rule no longer on that element and one fewer overall; judgment
findings: the same check re-run on the patched page), no axe rule's count increases, and the page
still renders (HTTP 200, no script errors, text retained). The pixel-diff ratio is recorded. Two
attempts per issue, with the failure reason fed back; then "needs human".

**Models (free tier, via LiteLLM).** Vision: `groq/qwen/qwen3.8-27b` (reads images; verified to
transcribe text in images). Text (link purpose, fixes): `groq/openai/gpt-oss-120b`, which has its
own rate limit. Both are env-configurable. Groq's free tier allows 8,000 tokens/minute and 1,000
requests/day per model, so crops are downscaled to 384 px, calls are serialised per model, 429s
honour `retry-after`, and responses are cached on disk with their original usage and latency
(re-runs report what the call cost when it was made).

**Cost.** Groq's public pricing page did not expose list prices to our fetch, so results report
model tokens per page and per 1,000 pages (measured), and dollars only from prices set in config.
The free tier costs $0.

## Phase 3 acceptance thresholds (agreed before results)
On the full benchmark, versus the axe-core baseline:
1. **Recall on judgment-based labels** rises from 0.000 to **≥ 0.60**.
2. **Overall precision on synthetic pages ≥ 0.90** (baseline 1.000).
3. **Precision of model-sourced predictions ≥ 0.85.**
4. **At most 1 false positive across the 5 clean control pages.**
5. Rule-detectable recall stays **1.000** (the agent must not lose what axe finds).
6. **Fix success rate** (successful / issues with an attempted fix) is reported; no threshold in
   Phase 3, because the denominator includes fixes that need human judgment.

If a threshold is missed, the result is reported as missed, with the failing slice.

## Consequences
- Judgment checks cost tokens and time (rate-limited free tier); the deterministic baseline stays
  available as `ramp audit`.
- Verification supports static sites whose repo is the served root. Framework apps need a build
  step before verification (roadmap).
