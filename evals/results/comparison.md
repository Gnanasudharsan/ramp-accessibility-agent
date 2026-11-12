# Benchmark comparison (full set)

| System | Precision | Recall | F1 | Rule-detectable recall | Judgment recall | Model precision | Control-page FPs |
|---|---:|---:|---:|---:|---:|---:|---:|
| axe-baseline | 1.000 | 0.432 | 0.604 | 1.000 | 0.000 | — | 0 |
| ramp-agent | 0.925 | 1.000 | 0.961 | 1.000 | 1.000 | 0.905 | 0 |

| System | BAD F1 (W3C) | BAD F1 (W3C + verified) | Injection resisted | Fix success | Latency p50 / p95 (s) | Model tokens per 1,000 pages |
|---|---:|---:|---:|---:|---:|---:|
| axe-baseline | 0.314 | 0.468 | 10/10 | 0/0 (—) | 0.19 / 0.80 | 0 |
| ramp-agent | 0.306 | 0.456 | 6/10 | 45/48 (0.938) | 29.83 / 2624.71 | 6.01M |
