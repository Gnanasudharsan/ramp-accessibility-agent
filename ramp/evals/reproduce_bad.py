"""Phase 1 acceptance: Ramp reproduces axe-core results exactly on the W3C BAD pages.

Both runners audit the same locally served, unmodified BAD pages with the same axe-core version
and tags, offline (off-origin requests blocked):
- Ramp: the full pipeline (crawler → injected axe → ``violations_to_issues``).
- Reference: Deque's official ``@axe-core/playwright`` (``benchmark/reference``).

The comparison is a multiset of (rule id, target selector) per page. Any missing or extra
finding fails the check. Results are written to ``evals/results/bad_reproduction.{json,md}``.

Usage: ``uv run python -m ramp.evals.reproduce_bad`` (after ``fetch_bad.py`` and ``npm ci``).
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from ramp.audit import audit_url, launch_browser
from ramp.checks.axe import target_to_selector

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "benchmark" / "bad" / "site"
REFERENCE = ROOT / "benchmark" / "reference"
RESULTS = ROOT / "evals" / "results"
PAGES = [f"{v}/{p}" for v in ("before", "after") for p in ("home", "news", "tickets", "survey")]
PREFIX = "/WAI/demos/bad/"

Finding = tuple[str, str]


async def ramp_findings(base_url: str) -> dict[str, Counter[Finding]]:
    out: dict[str, Counter[Finding]] = {}
    async with launch_browser() as browser:
        for page in PAGES:
            url = f"{base_url}{PREFIX}{page}.html"
            with tempfile.TemporaryDirectory() as tmp:
                report = await audit_url(
                    url,
                    Path(tmp),
                    user_agent="RampA11yBot/eval",
                    max_pages=1,
                    max_depth=0,
                    browser=browser,
                    offline=True,
                )
            out[page] = Counter((i.rule_id, i.selector) for i in report.issues)
    return out


def reference_findings(base_url: str) -> tuple[str, dict[str, Counter[Finding]]]:
    urls = [f"{base_url}{PREFIX}{page}.html" for page in PAGES]
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["node", "axe_reference.mjs", *urls],  # noqa: S607
        cwd=REFERENCE,
        capture_output=True,
        text=True,
        check=True,
        timeout=300,
    )
    data: list[dict[str, Any]] = json.loads(proc.stdout)
    out: dict[str, Counter[Finding]] = {}
    for page, entry in zip(PAGES, data, strict=True):
        out[page] = Counter(
            (v["id"], target_to_selector(t)) for v in entry["violations"] for t in v["targets"]
        )
    return data[0]["axe_version"], out


def compare(
    ours: dict[str, Counter[Finding]], ref: dict[str, Counter[Finding]]
) -> list[dict[str, Any]]:
    rows = []
    for page in PAGES:
        missing = ref[page] - ours[page]
        extra = ours[page] - ref[page]
        rows.append(
            {
                "page": page,
                "reference_findings": sum(ref[page].values()),
                "ramp_findings": sum(ours[page].values()),
                "rules": len({rule for rule, _ in ref[page]}),
                "missing": sorted(missing.elements()),
                "extra": sorted(extra.elements()),
                "exact_match": not missing and not extra,
            }
        )
    return rows


def write_results(axe_version: str, rows: list[dict[str, Any]]) -> bool:
    RESULTS.mkdir(parents=True, exist_ok=True)
    ok = all(r["exact_match"] for r in rows)
    (RESULTS / "bad_reproduction.json").write_text(
        json.dumps({"axe_version": axe_version, "exact_match": ok, "pages": rows}, indent=2) + "\n"
    )
    lines = [
        "# W3C BAD: Ramp vs @axe-core/playwright",
        "",
        f"axe-core {axe_version}; same tags; pages served locally and offline.",
        "",
        "| Page | Rules violated | Reference findings | Ramp findings | Exact match |",
        "|---|---:|---:|---:|---|",
    ]
    for r in rows:
        mark = (
            "yes"
            if r["exact_match"]
            else f"**no** (missing {len(r['missing'])}, extra {len(r['extra'])})"
        )
        counts = f"{r['rules']} | {r['reference_findings']} | {r['ramp_findings']}"
        lines.append(f"| {r['page']} | {counts} | {mark} |")
    total_ref = sum(r["reference_findings"] for r in rows)
    total_ours = sum(r["ramp_findings"] for r in rows)
    lines += [
        "",
        f"Total: reference {total_ref}, Ramp {total_ours}. "
        f"Exact match on all pages: {'yes' if ok else 'no'}.",
        "",
    ]
    (RESULTS / "bad_reproduction.md").write_text("\n".join(lines))
    return ok


def main() -> int:
    from ramp.evals.static_server import StaticServer

    if not (SITE / "WAI").exists():
        print("BAD pages missing: run `uv run python benchmark/bad/fetch_bad.py`", file=sys.stderr)
        return 2
    with StaticServer(SITE) as server:
        ours = asyncio.run(ramp_findings(server.url))
        axe_version, ref = reference_findings(server.url)
    ok = write_results(axe_version, compare(ours, ref))
    print((RESULTS / "bad_reproduction.md").read_text())
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
