# Load test: audit API

Run 2026-11-12T19:16:56+00:00 · 2 worker(s), 2 concurrent jobs each · 4 one-page audits per client · 1 target host(s), all a local static copy of the benchmark pages.

| Clients | Audits | Errors | Audits/min | Submit p50 / p95 (s) | Status read p50 / p95 (s) | End-to-end p50 / p95 (s) | Queue wait p50 / p95 (s) |
|---:|---:|---:|---:|---|---|---|---|
| 8 | 32 | 0 | 60.27 | 0.003 / 0.02 | 0.004 / 0.008 | 6.172 / 13.846 | 4.089 / 4.374 |

End-to-end time includes the crawler's politeness rules: a robots.txt fetch per audit and at most one page request per second per host, shared by every job and worker.
