"""Benchmark integrity: schema in sync, labels well-formed, pages match their specs."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from ramp.evals.labels import DetectableBy, json_schema, load_bad_labels, load_element_labels

BENCH = Path(__file__).parents[1] / "benchmark"


def _build_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_benchmark", BENCH / "build_benchmark.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_benchmark"] = module
    spec.loader.exec_module(module)
    return module


def test_committed_schema_matches_models() -> None:
    assert (BENCH / "schema" / "labels-v1.schema.json").read_text() == json_schema()


@pytest.mark.parametrize("name", ["synthetic", "adversarial"])
def test_element_labels_are_well_formed(name: str) -> None:
    labels = load_element_labels(BENCH / "labels" / f"{name}.json")
    ids = [lab.id for page in labels.pages for lab in page.labels]
    assert len(ids) == len(set(ids)), "label ids must be unique"
    for page in labels.pages:
        assert (BENCH / page.page).exists()
        selectors = [lab.selector for lab in page.labels]
        assert len(selectors) == len(set(selectors)), f"{page.page}: one label per element"


def test_benchmark_size_and_mix() -> None:
    synthetic = load_element_labels(BENCH / "labels" / "synthetic.json")
    assert len(synthetic.pages) >= 30
    by = [lab.detectable_by for page in synthetic.pages for lab in page.labels]
    assert by.count(DetectableBy.VISION) >= 15
    assert by.count(DetectableBy.RULE) >= 15
    assert sum(1 for page in synthetic.pages if not page.labels) >= 5  # clean controls


def test_adversarial_pages_really_contain_their_injection() -> None:
    adversarial = load_element_labels(BENCH / "labels" / "adversarial.json")
    canaries = set()
    for page in adversarial.pages:
        assert page.injection is not None
        canaries.add(page.injection.canary)
        if page.injection.vector != "image_text":
            assert page.injection.canary in (BENCH / page.page).read_text()
        assert page.labels, "every adversarial page has a real barrier that must still be found"
    assert len(canaries) == len(adversarial.pages)


def test_pages_are_up_to_date_with_specs() -> None:
    build = _build_module()
    specs = build.RULE_PAGES + build.VISION_PAGES + build.CONTROL_PAGES
    for spec in specs:
        assert (BENCH / "site" / "synthetic" / f"{spec.slug}.html").read_text() == build.render(
            spec
        )
    for spec in build.adversarial_specs():
        assert (BENCH / "site" / "adversarial" / f"{spec.slug}.html").read_text() == (
            build.render(spec)
        )


def test_bad_labels_separate_w3c_from_labeler() -> None:
    bad = load_bad_labels(BENCH / "labels" / "bad.json")
    assert len(bad.pages) == 8
    for page in bad.pages:
        if page.page.startswith("after/"):
            assert page.fails == []
        else:
            assert {f.source for f in page.fails} == {"w3c", "labeler"}
    raw = json.loads((BENCH / "labels" / "bad.json").read_text())
    assert raw["schema_version"] == "1.0"
