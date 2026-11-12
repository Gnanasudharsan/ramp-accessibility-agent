# ADR 0001 — Record architecture decisions

- Status: accepted
- Date: 2026-11-12

## Context
Ramp makes several non-obvious choices (model providers, evaluation thresholds, sandboxing). A
reviewer should be able to see why each was made and what was traded away.

## Decision
Keep short ADRs in `docs/adr/NNNN-title.md` with Context, Decision, Consequences. An ADR is written
when a choice is expensive to reverse or when a number (a threshold, a margin) is chosen.

## Consequences
Decisions are reviewable in pull requests alongside the code that implements them.
