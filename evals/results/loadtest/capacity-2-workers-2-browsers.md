# Load test: audit API

Run 2026-11-12T19:16:24+00:00 · 2 worker(s), 2 concurrent jobs each · 3 one-page audits per client · 8 target host(s), all a local static copy of the benchmark pages.

| Clients | Audits | Errors | Audits/min | Submit p50 / p95 (s) | Status read p50 / p95 (s) | End-to-end p50 / p95 (s) | Queue wait p50 / p95 (s) |
|---:|---:|---:|---:|---|---|---|---|
| 1 | 3 | 0 | 62.64 | 0.005 / 0.029 | 0.003 / 0.006 | 1.022 / 1.047 | 0.518 / 0.538 |
| 4 | 12 | 0 | 233.21 | 0.003 / 0.016 | 0.003 / 0.004 | 1.018 / 1.043 | 0.267 / 0.51 |
| 8 | 24 | 0 | 293.68 | 0.004 / 0.045 | 0.003 / 0.005 | 1.527 / 2.039 | 1.018 / 1.528 |
| 16 | 48 | 0 | 328.63 | 0.007 / 0.061 | 0.003 / 0.006 | 2.543 / 3.355 | 2.045 / 2.808 |

End-to-end time includes the crawler's politeness rules: a robots.txt fetch per audit and at most one page request per second per host, shared by every job and worker.
