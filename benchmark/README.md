# benchmark/

| Path | What |
|---|---|
| `build_benchmark.py` | Generates every synthetic and adversarial page **and** its labels from one spec list. |
| `site/synthetic/` | 37 pages: 16 with rule-detectable barriers, 16 with barriers that need judgment (alt quality, link purpose, images of text, focus visibility, captions cues), 5 clean controls. |
| `site/adversarial/` | 10 prompt-injection pages (alt, hidden div, comment, aria-label, visible text, title, text inside an image, link text, delimiter escape, meta) that also contain real barriers. |
| `site/assets/` | Shared CSS and drawn images (owned by this project). |
| `labels/` | `synthetic.json`, `adversarial.json` (element labels), `bad.json` (W3C BAD page × criterion). |
| `schema/labels-v1.schema.json` | JSON Schema for the label files (kept in sync by a test). |
| `bad/fetch_bad.py` | Polite download of the W3C BAD pages (gitignored, W3C Document License). |
| `reference/` | Deque's `@axe-core/playwright`, the independent reference for the Phase 1 reproduction check. |

How labels are written: [`docs/labeling-guidelines.md`](../docs/labeling-guidelines.md).
Pages are fictional ("Brightwater Library").
