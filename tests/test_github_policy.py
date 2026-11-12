from pathlib import Path

import pytest

from ramp.agent.fixes import local_path, served_file
from ramp.github.policy import PRLedger, evaluate_policy
from ramp.github.publish import ApprovedFix, apply_fixes, pr_body


def test_own_repo_is_allowed_without_disclosure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAMP_OWNED_OWNERS", "Gnanasudharsan")
    decision = evaluate_policy("gnanasudharsan", {})
    assert decision.allowed
    assert not decision.disclosure_required


@pytest.mark.parametrize(
    "text",
    [
        "Please do not submit AI-generated pull requests.",
        "AI-generated contributions will be rejected.",
        "We have a strict policy: no LLM-generated code.",
    ],
)
def test_projects_that_reject_ai_contributions_are_refused(text: str) -> None:
    decision = evaluate_policy("someone", {"CONTRIBUTING.md": text})
    assert not decision.allowed


def test_other_repos_always_get_disclosure() -> None:
    decision = evaluate_policy("someone", {"CONTRIBUTING.md": "Run the tests before a PR."})
    assert decision.allowed
    assert decision.disclosure_required


def test_ledger_allows_one_pr_per_repo_unless_invited(tmp_path: Path) -> None:
    ledger = PRLedger(path=tmp_path / "ledger.json")
    assert ledger.may_open("a/b")
    ledger.record("a/b", "https://github.com/a/b/pull/1")
    assert not ledger.may_open("A/B")
    assert ledger.may_open("a/b", invited=True)


def _fix(fid: str, old: str, new: str) -> ApprovedFix:
    return ApprovedFix(
        id=fid,
        file="index.html",
        old=old,
        new=new,
        explanation="Adds alt text.",
        issue_title="Image has no alt",
        criteria=["1.1.1"],
        page_path="/index.html",
        visual_diff_ratio=0.0,
    )


def test_apply_fixes_skips_conflicts(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text('<img src="a.png">\n<img src="b.png">\n')
    fixes = [
        _fix("1", '<img src="a.png">', '<img src="a.png" alt="A">'),
        _fix("2", '<img src="a.png">', '<img src="a.png" alt="Other">'),  # same code, now gone
        _fix("3", '<img src="b.png">', '<img src="b.png" alt="B">'),
    ]
    changed, skipped = apply_fixes(tmp_path, fixes)
    assert skipped == ["2"]
    assert changed["index.html"] == '<img src="a.png" alt="A">\n<img src="b.png" alt="B">\n'


def test_pr_body_states_limits_and_disclosure() -> None:
    from ramp.github.policy import PolicyDecision

    body = pr_body(
        [_fix("1", "a", "b")],
        {"remaining": 0, "new_violations": [], "renders": True},
        {"/index.html": ("https://x/before.png", "https://x/after.png")},
        PolicyDecision(True, "read", disclosure_required=True),
        ["1.2.1", "1.3.3"],
    )
    assert "not a statement of compliance" in body
    assert "AI disclosure" in body
    assert "![before](https://x/before.png)" in body
    assert "| Image has no alt | 1.1.1 | `index.html` | 0.00% |" in body


def test_local_path_and_served_file(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("x")
    (tmp_path / "a.html").write_text("x")
    url = "https://user.github.io/demo/a.html"
    assert local_path(url, "/demo/") == "/a.html"
    assert local_path("https://user.github.io/demo/", "/demo/") == "/"
    assert served_file(url, tmp_path, "/demo/") == "a.html"
    assert served_file("https://user.github.io/demo/", tmp_path, "/demo/") == "index.html"
