import json
from pathlib import Path
from typing import Any

from ramp.evals.gate import check, render

GATE = json.loads((Path(__file__).parents[1] / "evals" / "gate.json").read_text())


def _result(
    judgment_recall: float = 1.0, leaked: bool = False, failed: int = 0, control_fps: int = 0
) -> dict[str, Any]:
    return {
        "system": "ramp-agent",
        "subset": "smoke",
        "synthetic": {
            "overall": {"all": {"precision": 0.9}},
            "per_detectable_by": {"rule": {"recall": 1.0}, "vision": {"recall": judgment_recall}},
            "per_source": {"vision": {"tp": 3, "fp": 0, "precision": 1.0}},
            "false_positives": [f"site/synthetic/n01-x.html#{i}" for i in range(control_fps)],
        },
        "adversarial": {"pages": [{"canary_leaked": leaked}]},
        "failed_model_calls": failed,
    }


def test_good_run_passes() -> None:
    assert check(_result(), GATE)[0]


def test_degraded_judgment_is_blocked() -> None:
    passed, rows = check(_result(judgment_recall=1 / 3), GATE)
    assert not passed
    assert [r["metric"] for r in rows if not r["ok"]] == ["judgment_recall"]


def test_canary_leak_and_control_false_positives_are_blocked() -> None:
    assert not check(_result(leaked=True), GATE)[0]
    assert not check(_result(control_fps=2), GATE)[0]


def test_failed_model_calls_are_inconclusive_not_a_pass() -> None:
    passed, rows = check(_result(failed=2), GATE)
    assert not passed
    assert "inconclusive" in render(passed, rows, _result(failed=2))
