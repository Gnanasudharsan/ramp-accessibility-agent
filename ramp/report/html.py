"""Render an AuditReport as a self-contained, accessible HTML page."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from ramp.checks.wcag import CRITERIA
from ramp.report.schema import AuditReport, Issue, Severity

_env = Environment(
    loader=PackageLoader("ramp.report", "templates"),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_html(report: AuditReport) -> str:
    issues = sorted(report.issues, key=lambda i: (i.severity.rank, i.rule_id, i.page_url))
    by_severity = Counter(i.severity for i in issues)
    by_rule: dict[str, list[Issue]] = defaultdict(list)
    for issue in issues:
        by_rule[issue.rule_id].append(issue)
    return _env.get_template("report.html").render(
        report=report,
        issues=issues,
        by_rule=dict(by_rule),
        severities=list(Severity),
        by_severity=by_severity,
        criteria=CRITERIA,
    )


def write_reports(report: AuditReport, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "report.json"
    html_path = out_dir / "report.html"
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    html_path.write_text(render_html(report), encoding="utf-8")
    return json_path, html_path
