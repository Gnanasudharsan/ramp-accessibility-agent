from training.build_dataset import Record, split_ids
from training.eval_student import parse_problem, score


def _record(i: int) -> Record:
    return Record(
        image_id=f"c{i:04d}",
        file=f"images/c{i:04d}.jpg",
        title="t",
        description="d",
        license="CC0",
        license_url="",
        author="",
        source_url="",
    )


def test_split_is_by_image_deterministic_and_disjoint() -> None:
    records = [_record(i) for i in range(50)]
    a, b = split_ids(records), split_ids(list(reversed(records)))
    assert a == b  # order of the manifest does not change the split
    assert not (a["train"] & a["test"])
    assert not (a["valid"] & a["test"])
    assert sum(len(v) for v in a.values()) == 50
    assert len(a["test"]) == 5


def test_parse_problem() -> None:
    assert parse_problem('{"problem": "generic", "suggested_alt": "x"}') == "generic"
    assert parse_problem('Sure! {"problem": "filename"}') == "filename"
    assert parse_problem('{"problem": "bogus"}') is None
    assert parse_problem("not json") is None


def test_score_counts_unparsed_as_wrong() -> None:
    result = score(["none", "generic", "filename"], ["none", None, "generic"])
    assert result["accuracy"] == 1 / 3
    assert result["parse_rate"] == 2 / 3
    assert result["per_class"]["generic"]["precision"] == 0.0
    assert result["confusion"]["generic"] == {"None": 1}
