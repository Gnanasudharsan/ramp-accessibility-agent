from ramp.evals.metrics import PRF, GoldItem, PredItem, match, page_criterion_prf, percentile, score


def gold(lid: str, key: str, crit: str, by: str = "rule", also: tuple[str, ...] = ()) -> GoldItem:
    return GoldItem("p", key, crit, frozenset({crit, *also}), by, lid)


def pred(iid: str, key: str, *crits: str, source: str = "rule") -> PredItem:
    return PredItem("p", key, crits, source, iid)


def test_match_requires_same_element_and_overlapping_criteria() -> None:
    g = [gold("l1", "#a", "2.4.4", also=("4.1.2",)), gold("l2", "#b", "1.1.1")]
    p = [pred("i1", "#a", "4.1.2"), pred("i2", "#b", "1.4.3"), pred("i3", "#a", "2.4.4")]
    result = match(g, p)
    assert result.matched_labels == {"l1": "i1"}
    assert [x.issue_id for x in result.false_positives] == ["i2"]
    assert [x.issue_id for x in result.duplicates] == ["i3"]  # not double-counted as FP


def test_scores_by_slice() -> None:
    g = [gold("l1", "#a", "1.1.1"), gold("l2", "#b", "1.1.1", by="vision")]
    p = [pred("i1", "#a", "1.1.1"), pred("i2", "#c", "1.4.3", source="vision")]
    s = score(g, p, match(g, p))
    overall = s["overall"]["all"]
    assert (overall.tp, overall.fp, overall.fn) == (1, 1, 1)
    assert s["per_detectable_by"]["vision"].recall == 0.0
    assert s["per_criterion"]["1.4.3"].fp == 1
    assert s["per_source"]["vision"].precision == 0.0
    assert s["per_source"]["rule"].precision == 1.0


def test_prf_edge_cases() -> None:
    assert PRF().precision is None
    assert PRF(fn=2).recall == 0.0
    assert PRF(tp=1, fp=1, fn=1).f1 == 0.5


def test_page_criterion_prf() -> None:
    m = page_criterion_prf({"a": {"1.1.1", "2.4.4"}, "b": set()}, {"a": {"1.1.1"}, "b": {"3.1.1"}})
    assert (m.tp, m.fp, m.fn) == (1, 1, 1)


def test_percentile() -> None:
    assert percentile([], 50) is None
    assert percentile([3.0, 1.0, 2.0], 50) == 2.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 95) == 4.0
