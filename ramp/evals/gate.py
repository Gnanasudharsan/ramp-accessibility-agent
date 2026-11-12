"""Eval gate: ``uv run python -m ramp.evals.gate`` after the runner, in CI (Phase 6).

Reads ``evals/gate.json`` and the runner's result file, checks each metric against its bar, and
exits non-zero if any bar is missed, so a prompt or model change that lowers quality cannot merge.
A run with failed model calls is *inconclusive* and also fails: skipped checks can only make a
change look safer than it is.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def metrics(result: dict[str, Any]) -> dict[str, float | None]:
    syn = result["synthetic"]
    detect = syn["per_detectable_by"]
    model = syn["per_source"].get("vision", {})
    model_predictions = model.get("tp", 0) + model.get("fp", 0)
    adversarial = result.get("adversarial", {}).get("pages", [])
    return {
        "judgment_recall": detect.get("vision", {}).get("recall"),
        "rule_recall": detect.get("rule", {}).get("recall"),
        "precision": syn["overall"]["all"]["precision"],
        "model_precision": model.get("precision") if model_predictions else None,
        "control_false_positives": float(sum(1 for fp in syn["false_positives"] if "/n0" in fp)),
        "canary_leaks": float(sum(1 for p in adversarial if p.get("canary_leaked"))),
        "failed_model_calls": float(result.get("failed_model_calls", 0)),
    }


def check(result: dict[str, Any], gate: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    """Return (passed, rows). A metric that does not apply (None) passes its bar."""
    values = metrics(result)
    rows = []
    for bound, op in (("min", ">="), ("max", "<=")):
        for name, bar in gate.get(bound, {}).items():
            value = values.get(name)
            ok = value is None or (value >= bar if bound == "min" else value <= bar)
            rows.append({"metric": name, "value": value, "bar": f"{op} {bar}", "ok": ok})
    return all(r["ok"] for r in rows), rows


def render(passed: bool, rows: list[dict[str, Any]], result: dict[str, Any]) -> str:
    inconclusive = any(r["metric"] == "failed_model_calls" and not r["ok"] for r in rows)
    verdict = (
        "passed" if passed else ("inconclusive (model calls failed)" if inconclusive else "FAILED")
    )
    lines = [
        f"## Eval gate: {verdict}",
        "",
        f"`{result['system']}` on the `{result['subset']}` subset · prompts: "
        + ", ".join(result.get("models", {}).get("prompts", [])),
        "",
        "| Metric | Value | Bar | |",
        "|---|---:|---|---|",
    ]
    for r in rows:
        value = "n/a" if r["value"] is None else f"{r['value']:.3f}".rstrip("0").rstrip(".")
        lines.append(f"| {r['metric']} | {value} | {r['bar']} | {'pass' if r['ok'] else 'FAIL'} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    gate = json.loads((ROOT / "evals" / "gate.json").read_text())
    path = ROOT / "evals" / "results" / gate["system"] / f"{gate['subset']}.json"
    result = json.loads(path.read_text())
    passed, rows = check(result, gate)
    text = render(passed, rows, result)
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
