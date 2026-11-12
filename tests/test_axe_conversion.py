from ramp.checks.axe import AxeResults, target_to_selector, violations_to_issues
from ramp.report.schema import DetectionSource, Severity

RAW = {
    "axe_version": "4.14.0",
    "url": "https://x.org/",
    "violations": [
        {
            "id": "image-alt",
            "impact": "critical",
            "tags": ["cat.text-alternatives", "wcag2a", "wcag111", "section508"],
            "help": "Images must have alternative text",
            "helpUrl": "https://dequeuniversity.com/rules/axe/4.14/image-alt",
            "nodes": [
                {
                    "target": ["#a"],
                    "html": "<img id=a>",
                    "failureSummary": "Fix",
                    "impact": "critical",
                },
                {
                    "target": ["#b"],
                    "html": "<img id=b>",
                    "failureSummary": "Fix",
                    "impact": "critical",
                },
            ],
        },
        {
            "id": "region",
            "impact": "moderate",
            "tags": ["cat.keyboard", "best-practice"],
            "help": "All page content should be contained by landmarks",
            "helpUrl": "https://dequeuniversity.com/rules/axe/4.14/region",
            "nodes": [{"target": [["iframe", "#inner"]], "html": "<p>", "failureSummary": ""}],
        },
    ],
    "incomplete": [],
}


def test_conversion_is_lossless_one_issue_per_node() -> None:
    issues = violations_to_issues(AxeResults.model_validate(RAW), "https://x.org/")
    assert len(issues) == 3
    assert [i.selector for i in issues] == ["#a", "#b", "iframe >>> #inner"]
    assert all(i.source is DetectionSource.RULE and i.confidence == 1.0 for i in issues)


def test_criteria_and_severity_mapping() -> None:
    image, _, region = violations_to_issues(AxeResults.model_validate(RAW), "https://x.org/")
    assert image.criteria == ["1.1.1"]
    assert image.severity is Severity.CRITICAL
    assert region.criteria == []  # best practice, never reported as a WCAG failure
    assert region.severity is Severity.MODERATE


def test_issue_ids_are_stable_and_distinct() -> None:
    first = violations_to_issues(AxeResults.model_validate(RAW), "https://x.org/")
    second = violations_to_issues(AxeResults.model_validate(RAW), "https://x.org/")
    assert [i.id for i in first] == [i.id for i in second]
    assert len({i.id for i in first}) == 3


def test_target_to_selector() -> None:
    assert target_to_selector(["#a"]) == "#a"
    assert target_to_selector([["#host", "button"]]) == "#host >>> button"
