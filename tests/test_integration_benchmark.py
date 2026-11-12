"""Label quality gate: the deterministic baseline must agree with how pages are labeled.

- every label marked ``rule`` is found by axe-core (else it is mislabeled, or the page is broken)
- no label marked ``vision`` is found by axe-core (else it belongs in ``rule``)
- axe-core reports no WCAG finding that is not labeled (labels are complete)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ramp.audit import launch_browser
from ramp.evals.labels import load_element_labels
from ramp.evals.metrics import match
from ramp.evals.runner import BENCH, run_element_set
from ramp.evals.static_server import StaticServer
from ramp.evals.systems import AxeBaseline

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("name", ["synthetic", "adversarial"])
async def test_labels_agree_with_rule_engine(name: str) -> None:
    labels = load_element_labels(BENCH / "labels" / f"{name}.json")
    async with launch_browser() as browser:
        with StaticServer(Path(BENCH / "site")) as server:
            gold, preds, _, problems = await run_element_set(
                AxeBaseline(), browser, server.url, labels
            )
    assert problems == []
    result = match(gold, preds)
    found = set(result.matched_labels)
    rule = {g.label_id for g in gold if g.detectable_by == "rule"}
    vision = {g.label_id for g in gold if g.detectable_by == "vision"}
    assert rule - found == set(), "rule labels axe did not find"
    assert vision & found == set(), "vision labels axe found (relabel as rule)"
    assert [p.issue_id for p in result.false_positives] == [], "unlabeled axe findings"
