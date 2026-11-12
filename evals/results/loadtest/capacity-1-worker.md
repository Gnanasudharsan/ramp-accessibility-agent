# Load test: audit API

Run 2026-11-12T19:12:23+00:00 · 1 worker(s), 2 concurrent jobs each · 3 one-page audits per client · 8 target host(s), all a local static copy of the benchmark pages.

| Clients | Audits | Errors | Audits/min | Submit p50 / p95 (s) | Status read p50 / p95 (s) | End-to-end p50 / p95 (s) | Queue wait p50 / p95 (s) |
|---:|---:|---:|---:|---|---|---|---|
| 1 | 3 | 0 | 68.75 | 0.003 / 0.029 | 0.003 / 0.007 | 0.795 / 1.023 | 0.515 / 0.516 |
| 4 | 12 | 0 | 133.74 | 0.003 / 0.015 | 0.003 / 0.006 | 2.04 / 2.045 | 1.532 / 1.535 |
| 8 | 24 | 0 | 118.89 | 0.005 / 0.026 | 0.004 / 0.01 | 3.859 / 4.122 | 3.346 / 3.606 |
| 16 | 48 | 0 | 123.52 | 0.005 / 0.08 | 0.003 / 0.009 | 7.659 / 8.166 | 6.899 / 7.65 |

End-to-end time includes the crawler's politeness rules: a robots.txt fetch per audit and at most one page request per second per host, shared by every job and worker.
