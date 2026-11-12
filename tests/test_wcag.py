from ramp.checks.wcag import CRITERIA, criteria_from_axe_tags, criterion_from_axe_tag


def test_catalog_counts_match_wcag_22_a_and_aa() -> None:
    # WCAG 2.2 has 55 A/AA criteria once 4.1.1 Parsing (obsolete) is removed.
    assert len(CRITERIA) == 55
    assert sum(c.version == "2.2" for c in CRITERIA.values()) == 6
    assert all(c.in_target for c in CRITERIA.values() if c.version != "2.2")


def test_tag_parsing_handles_two_digit_criteria() -> None:
    assert criterion_from_axe_tag("wcag111") == "1.1.1"
    assert criterion_from_axe_tag("wcag1412") == "1.4.12"
    assert criterion_from_axe_tag("wcag258") == "2.5.8"
    assert criterion_from_axe_tag("wcag21aa") is None
    assert criterion_from_axe_tag("best-practice") is None


def test_criteria_from_tags_drops_obsolete_parsing_and_keeps_catalog_order() -> None:
    tags = ["wcag2a", "wcag412", "wcag411", "wcag131", "cat.aria"]
    assert criteria_from_axe_tags(tags) == ["1.3.1", "4.1.2"]


def test_understanding_url() -> None:
    assert CRITERIA["1.4.3"].understanding_url.endswith("/contrast-minimum.html")
