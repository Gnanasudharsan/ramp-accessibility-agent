# Load test: audit API

Run 2026-11-12T19:15:52+00:00 · 2 worker(s), 2 concurrent jobs each · 3 one-page audits per client · 8 target host(s), all a local static copy of the benchmark pages.

| Clients | Audits | Errors | Audits/min | Submit p50 / p95 (s) | Status read p50 / p95 (s) | End-to-end p50 / p95 (s) | Queue wait p50 / p95 (s) |
|---:|---:|---:|---:|---|---|---|---|
| 1 | 3 | 0 | 62.19 | 0.007 / 0.031 | 0.003 / 0.006 | 1.027 / 1.053 | 0.287 / 0.52 |
| 4 | 12 | 0 | 140.35 | 0.004 / 0.018 | 0.003 / 0.007 | 1.784 / 2.06 | 0.269 / 0.528 |
| 8 | 24 | 0 | 146.88 | 0.004 / 0.035 | 0.004 / 0.011 | 3.092 / 3.88 | 1.797 / 2.324 |
| 16 | 48 | 0 | 150.97 | 0.005 / 0.058 | 0.004 / 0.009 | 5.875 / 7.199 | 4.87 / 5.887 |

End-to-end time includes the crawler's politeness rules: a robots.txt fetch per audit and at most one page request per second per host, shared by every job and worker.
