# ADR 0003 — Deterministic baseline: vendored axe-core, polite read-only crawler, MCP tools

- Status: accepted
- Date: 2026-11-12

## Context
Phase 1 is the baseline every model-based feature is measured against, so it must be exactly
reproducible and safe to point at sites we do not own.

## Decisions
1. **Vendor axe-core 4.14.0** (`ramp/checks/vendor/axe.min.js`, MPL-2.0, license kept beside it)
   rather than fetching it at runtime. The rule set is pinned to the commit; upgrading axe is a
   reviewed diff whose effect shows up in the benchmark.
2. **"Reproduces axe-core exactly" is tested against an independent runner**: Deque's
   `@axe-core/playwright` (Node, `benchmark/reference`). We compare the multiset of
   (rule id, target selector) per page; any missing or extra finding fails CI. Comparing against
   our own axe call would be circular.
3. **Same tags everywhere**: `wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa, best-practice`.
   Best-practice findings are kept but carry no WCAG criterion, so they never count as WCAG failures.
4. **Offline eval mode** blocks every off-origin request in both runners. The BAD pages embed a
   W3C analytics pixel; blocking it removes a network dependency and a tracking request.
5. **Read-only at the network layer**: the browser context aborts any non-GET/HEAD request. This
   blocks form submission *and* state-changing requests made by page scripts, which a "we never
   click submit" policy alone would not.
6. **robots.txt via protego**, following RFC 9309: 4xx means no restrictions; 5xx or a network
   error means disallow all. The standard-library parser ignores `*`/`$` wildcards (w3.org uses
   them), which would under-block. Crawl delay = max(1 s, `Crawl-delay`).
7. **Rate limit applies to page navigations**, one per second per host. Sub-resources a page
   loads (CSS, images) are what any browser loads for that one page view.
8. **`map_to_source` is deterministic scoring, not a model**: parse the element's opening tag and
   score source lines by distinctive attributes (id > src/href/name > alt > class > text). It is
   explainable, testable, and good enough to anchor a patch; the agent (Phase 3) can still refuse a
   low-score match. The MCP tool only reads under `RAMP_MCP_SOURCE_ROOTS`.
9. **MCP SDK v2** (`mcp>=2.3`, `MCPServer`, formerly FastMCP). Tools return Pydantic models, so
   clients get structured content and a schema.

## Consequences
- Upgrading axe changes baseline numbers by design; the reproduction check catches integration drift.
- iframes are audited by injecting axe into every frame; targets inside iframes or shadow DOM are
  flattened with ` >>> ` and get no screenshot crop.
