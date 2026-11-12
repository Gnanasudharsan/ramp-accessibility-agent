"""Score a small vision model on the alt-text test split (Phase 5).

Labels are the *constructed* ones from ``build_dataset.py`` (a real description, a camera file
name, a generic word, another image's description), so neither the teacher nor the student
produced them. The same file scores the teacher's verdicts when they exist, which puts teacher,
zero-shot student, and fine-tuned student on one scale.

Usage:
    uv run --group training python -m training.eval_student \
        --model mlx-community/Qwen3.5-0.8B-bf16 [--adapter DIR] --name qwen-zs
    uv run --group training python -m training.eval_student --teacher

Results go to ``evals/results/distill/<name>.json`` (and MLflow when ``MLFLOW_TRACKING_URI``
is set).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

DATA = Path(__file__).parent / "data"
RESULTS = Path(__file__).resolve().parents[1] / "evals" / "results" / "distill"
LABELS = ["none", "filename", "generic", "wrong_description"]


def load_test() -> list[dict[str, Any]]:
    path = DATA / "test.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def parse_problem(text: str) -> str | None:
    """The ``problem`` field from a model reply; None when the reply is not usable JSON."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            value = json.loads(match.group(0)).get("problem")
        except (json.JSONDecodeError, AttributeError):
            value = None
        if value in LABELS:
            return str(value)
    return None


def score(gold: list[str], pred: list[str | None]) -> dict[str, Any]:
    """Accuracy, macro F1, per-class P/R/F1, and how often the reply could be parsed.

    An unparseable reply counts as wrong (it would be a failed check in the agent)."""
    per_class: dict[str, dict[str, float]] = {}
    for label in LABELS:
        tp = sum(1 for g, p in zip(gold, pred, strict=True) if g == label and p == label)
        fp = sum(1 for g, p in zip(gold, pred, strict=True) if g != label and p == label)
        fn = sum(1 for g, p in zip(gold, pred, strict=True) if g == label and p != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[label] = {"precision": precision, "recall": recall, "f1": f1, "support": tp + fn}
    n = len(gold)
    return {
        "n": n,
        "accuracy": sum(1 for g, p in zip(gold, pred, strict=True) if g == p) / n if n else 0.0,
        "macro_f1": sum(c["f1"] for c in per_class.values()) / len(LABELS),
        "parse_rate": sum(1 for p in pred if p is not None) / n if n else 0.0,
        "per_class": per_class,
        "confusion": {
            g: dict(Counter(str(p) for gg, p in zip(gold, pred, strict=True) if gg == g))
            for g in LABELS
        },
    }


def run_student(model_id: str, adapter: str | None, items: list[dict[str, Any]]) -> dict[str, Any]:
    import mlx_vlm
    from mlx_vlm.prompt_utils import apply_chat_template

    from training.build_dataset import STUDENT_PROMPT

    # mlx-vlm's type hints do not line up with what load() returns; keep the boundary untyped.
    vlm: Any = mlx_vlm
    model, processor = vlm.load(model_id, adapter_path=adapter) if adapter else vlm.load(model_id)
    generate = vlm.generate
    preds: list[str | None] = []
    latencies: list[float] = []
    for item in items:
        prompt = apply_chat_template(
            processor, model.config, STUDENT_PROMPT + json.dumps(item["alt"]), num_images=1
        )
        started = time.perf_counter()
        out = generate(
            model, processor, prompt, image=[item["image"]], max_tokens=80, temperature=0.0
        )
        latencies.append(time.perf_counter() - started)
        preds.append(parse_problem(getattr(out, "text", str(out))))
    latencies.sort()
    return {
        "preds": preds,
        "latency_p50_s": latencies[len(latencies) // 2] if latencies else None,
        "latency_p95_s": latencies[int(0.95 * (len(latencies) - 1))] if latencies else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="mlx-community/Qwen3.5-0.8B-bf16")
    parser.add_argument("--adapter", default=None)
    parser.add_argument("--name", default=None)
    parser.add_argument("--teacher", action="store_true", help="Score the teacher's verdicts.")
    args = parser.parse_args()

    items = load_test()
    gold = [item["label"] for item in items]
    if args.teacher:
        name = args.name or "teacher"
        preds: list[str | None] = [
            item["teacher"] if item.get("teacher") in LABELS else None for item in items
        ]
        extra: dict[str, Any] = {"model": "teacher (see manifest)"}
    else:
        name = args.name or Path(args.adapter or args.model).name
        run = run_student(args.model, args.adapter, items)
        preds = run.pop("preds")
        extra = {"model": args.model, "adapter": args.adapter, **run}
    result = {"name": name, **extra, **score(gold, preds)}
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{name}.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("name", "n", "accuracy", "macro_f1", "parse_rate")}))

    if os.environ.get("MLFLOW_TRACKING_URI"):
        import mlflow

        mlflow.set_experiment("ramp-alt-text-judge")
        with mlflow.start_run(run_name=name):
            mlflow.log_params({k: str(v) for k, v in extra.items() if "latency" not in k})
            mlflow.log_metrics(
                {
                    "accuracy": result["accuracy"],
                    "macro_f1": result["macro_f1"],
                    "parse_rate": result["parse_rate"],
                }
            )


if __name__ == "__main__":
    main()
