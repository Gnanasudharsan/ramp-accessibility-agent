from datetime import UTC, datetime
from pathlib import Path

from ramp.report.html import render_html, write_reports
from ramp.report.schema import (
    AuditReport,
    Coverage,
    DetectionSource,
    Evidence,
    Issue,
    PageResult,
    Severity,
)


def _report() -> AuditReport:
    issue = Issue(
        id=Issue.make_id("https://x.org/", "image-alt", "#a"),
        rule_id="image-alt",
        title="Images must have alternative text",
        criteria=["1.1.1"],
        severity=Severity.CRITICAL,
        page_url="https://x.org/",
        selector="#a",
        evidence=Evidence(html_snippet="<img id=a src=x.png><script>alert(1)</script>"),
        source=DetectionSource.RULE,
        confidence=1.0,
    )
    now = datetime(2026, 11, 12, tzinfo=UTC)
    return AuditReport(
        target="https://x.org/",
        started_at=now,
        finished_at=now,
        ramp_version="0.0.0",
        pages=[
            PageResult(
                url="https://x.org/", final_url="https://x.org/", title="X", depth=0, issues=[issue]
            )
        ],
        coverage=Coverage(
            axe_version="4.14.0",
            axe_tags=["wcag2a"],
            axe_rules_run=1,
            criteria_checked=["1.1.1"],
            criteria_not_checked=["1.2.2"],
        ),
    )


def test_json_round_trip(tmp_path: Path) -> None:
    json_path, _ = write_reports(_report(), tmp_path)
    loaded = AuditReport.model_validate_json(json_path.read_text())
    assert loaded == _report()


def test_html_is_accessible_and_escapes_page_content() -> None:
    html = render_html(_report())
    assert '<html lang="en">' in html
    assert "Not a compliance statement" in html
    assert "<script>alert(1)</script>" not in html  # untrusted snippet is escaped
    assert "&lt;script&gt;" in html
    assert "1.2.2 Captions (Prerecorded)" in html  # not-checked criteria are listed
    assert 'scope="col"' in html
