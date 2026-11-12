"""Compare systems on the benchmark: ``uv run python -m ramp.evals.compare``.

Reads ``evals/results/<system>/full.json`` for every system present and writes
``evals/results/comparison.md`` and ``comparison.json``. README tables are copied from this
output, so every number in the README traces back to a results file produced by the runner.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

RESULTS = Path(__file__).resolve().parents[2] / "evals" / "results"
ORDER = ["axe-baseline", "ramp-agent", "ramp-distilled", "ramp-router"]


def _fmt(x: float | None, digits: int = 3) -> str:
    return "—" if x is None else f"{x:.{digits}f}"


def load(subset: str = "full") -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for name in ORDER:
        path = RESULTS / name / f"{subset}.json"
        if path.exists():
            found[name] = json.loads(path.read_text())
    return found


def rows(results: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for name, r in results.items():
        syn = r["synthetic"]
        detect = syn["per_detectable_by"]
        controls_fp = sum(1 for fp in syn["false_positives"] if "/n0" in fp)
        out.append(
            {
                "system": name,
                "precision": syn["overall"]["all"]["precision"],
                "recall": syn["overall"]["all"]["recall"],
                "f1": syn["overall"]["all"]["f1"],
                "rule_recall": detect.get("rule", {}).get("recall"),
                "judgment_recall": detect.get("vision", {}).get("recall"),
                "model_precision": syn["per_source"].get("vision", {}).get("precision"),
                "control_fps": controls_fp,
                "bad_f1_w3c": r["bad"]["w3c_only"]["f1"],
                "bad_f1_verified": r["bad"]["w3c_plus_verified"]["f1"],
                "bad_recall_verified": r["bad"]["w3c_plus_verified"]["recall"],
                "injection_rate": r["adversarial"]["rate"],
                "injection": f"{r['adversarial']['resisted']}/{r['adversarial']['total']}",
                "fix_rate": r["fixes"]["success_rate"],
                "fixes": f"{r['fixes']['succeeded']}/{r['fixes']['attempted']}",
                "p50": r["latency"]["p50_s"],
                "p95": r["latency"]["p95_s"],
                "tokens_per_1000": r["cost"].get("tokens_per_1000_pages", 0.0),
                "failed_calls": r.get("failed_model_calls", 0),
            }
        )
    return out


def markdown(table: list[dict[str, Any]]) -> str:
    lines = [
        "# Benchmark comparison (full set)",
        "",
        "| System | Precision | Recall | F1 | Rule-detectable recall | Judgment recall | "
        "Model precision | Control-page FPs |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in table:
        lines.append(
            f"| {r['system']} | {_fmt(r['precision'])} | {_fmt(r['recall'])} | {_fmt(r['f1'])} | "
            f"{_fmt(r['rule_recall'])} | {_fmt(r['judgment_recall'])} | "
            f"{_fmt(r['model_precision'])} | {r['control_fps']} |"
        )
    lines += [
        "",
        "| System | BAD F1 (W3C) | BAD F1 (W3C + verified) | Injection resisted | "
        "Fix success | Latency p50 / p95 (s) | Model tokens per 1,000 pages |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in table:
        tokens = r["tokens_per_1000"]
        token_text = "0" if not tokens else f"{tokens / 1e6:.2f}M"
        lines.append(
            f"| {r['system']} | {_fmt(r['bad_f1_w3c'])} | {_fmt(r['bad_f1_verified'])} | "
            f"{r['injection']} | {r['fixes']} ({_fmt(r['fix_rate'])}) | "
            f"{_fmt(r['p50'], 2)} / {_fmt(r['p95'], 2)} | {token_text} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    table = rows(load())
    (RESULTS / "comparison.json").write_text(json.dumps(table, indent=2) + "\n")
    text = markdown(table)
    (RESULTS / "comparison.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
