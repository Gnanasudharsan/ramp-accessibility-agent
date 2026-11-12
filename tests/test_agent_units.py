from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ramp.agent.collect import LinkCandidate, PageEvidence, StructureCandidate
from ramp.agent.fixes import ProposedFix, validate_patch
from ramp.agent.graph import AuditState, _use, after_verify, human_review, merge_and_dedupe
from ramp.agent.vision import (
    LinkJudgment,
    LinkJudgments,
    StructureJudgment,
    StructureJudgments,
    VisionChecker,
)
from ramp.models.llm import Transcript
from ramp.report.schema import DetectionSource, Evidence, Issue, Severity


def _issue(rule: str, crit: list[str], source: DetectionSource, key: str = "#a") -> Issue:
    return Issue(
        id=Issue.make_id("u", rule, key),
        rule_id=rule,
        title=rule,
        criteria=crit,
        severity=Severity.SERIOUS,
        page_url="u",
        selector=key,
        element_key=key,
        evidence=Evidence(html_snippet="<img>"),
        source=source,
        confidence=1.0,
    )


def test_validate_patch() -> None:
    src = '<img src="a.png">\n<img src="b.png">\n'
    assert validate_patch(src, '<img src="a.png">', '<img src="a.png" alt="A">') is None
    assert "not an exact substring" in (validate_patch(src, "<video>", "x") or "")
    assert "occurs 2 times" in (validate_patch(src, "<img", "<img alt") or "")
    assert "scripts" in (validate_patch(src, '<img src="a.png">', "<script>x</script>") or "")
    assert "identical" in (validate_patch(src, "a", "a") or "")


async def test_merge_marks_rule_and_vision_on_same_element_as_both() -> None:
    state = AuditState(
        url="u",
        out_dir="o",
        rule_issues=[_issue("image-alt", ["1.1.1"], DetectionSource.RULE)],
        vision_issues=[
            _issue("ramp-image-alt-quality", ["1.1.1"], DetectionSource.VISION),
            _issue("ramp-link-purpose", ["2.4.4"], DetectionSource.VISION, key="#b"),
        ],
    )
    merged = (await merge_and_dedupe(state))["issues"]
    assert [i.source for i in merged] == [DetectionSource.BOTH, DetectionSource.VISION]


def _fix(issue_id: str, status: str, attempt: int) -> ProposedFix:
    return ProposedFix(
        id=f"{issue_id}-{attempt}",
        issue_id=issue_id,
        file="f",
        line=1,
        old="a",
        new="b",
        explanation="",
        diff="d",
        attempt=attempt,
        status=status,
    )


def test_repair_loop_stops_after_two_attempts() -> None:
    once = AuditState(url="u", out_dir="o", fixes=[_fix("x", "failed", 1)])
    assert after_verify(once) == "generate_fixes"
    twice = AuditState(url="u", out_dir="o", fixes=[_fix("x", "failed", 1), _fix("x", "failed", 2)])
    assert after_verify(twice) == "human_review"
    fixed = AuditState(
        url="u", out_dir="o", fixes=[_fix("x", "failed", 1), _fix("x", "verified", 2)]
    )
    assert after_verify(fixed) == "human_review"


async def test_review_modes_never_approve_unverified() -> None:
    fixes = [_fix("x", "verified", 1), _fix("y", "failed", 2)]
    auto = AuditState(url="u", out_dir="o", fixes=fixes, review_mode="auto_approve")
    assert (await human_review(auto))["approved_fix_ids"] == ["x-1"]
    reject = AuditState(url="u", out_dir="o", fixes=fixes, review_mode="auto_reject")
    assert (await human_review(reject))["approved_fix_ids"] == []


def test_tool_allowlist_flags_tools_outside_the_node() -> None:
    assert _use("vision_checks", "llm.vision").allowed
    assert not _use("vision_checks", "github.open_pr").allowed
    assert not _use("crawl", "llm.text").allowed


class _FakeLLM:
    def __init__(self, reply: BaseModel) -> None:
        self.reply = reply
        self.transcript = Transcript()

    async def complete(self, **_: Any) -> BaseModel:
        return self.reply


async def test_vision_output_is_validated_against_candidates(tmp_path: Path) -> None:
    links = LinkJudgments(
        items=[
            LinkJudgment(cid="link1", purpose_clear=False, problem="ambiguous", confidence=0.9),
            LinkJudgment(cid="link99", purpose_clear=False, problem="ambiguous", confidence=0.9),
            LinkJudgment(cid="link2", purpose_clear=False, problem="ambiguous", confidence=0.2),
        ]
    )
    structure = StructureJudgments(
        items=[
            StructureJudgment(cid="s1", is_barrier=True, criterion="4.1.2", confidence=0.99),
            StructureJudgment(cid="s2", is_barrier=True, criterion="1.3.1", confidence=0.9),
        ]
    )
    (tmp_path / "page.png").write_bytes(b"")
    evidence = PageEvidence(
        url="u",
        title="t",
        screenshot_path="page.png",
        links=[
            LinkCandidate(
                cid=f"link{i}",
                selector=f"#l{i}",
                html="<a>",
                name="Click here",
                href="x.html",
                context="",
                heading="",
            )
            for i in (1, 2)
        ],
        structure=[
            StructureCandidate(
                cid=f"s{i}", selector=f"#s{i}", kind="heading_like", html="<div>", text="Events"
            )
            for i in (1, 2)
        ],
    )
    checker = VisionChecker(_FakeLLM(structure), _FakeLLM(links), tmp_path, 0.6)  # type: ignore[arg-type]
    checker.judge_structure = _fake_structure(structure)  # type: ignore[method-assign]
    issues = await checker.check_page(evidence, "u")
    found = {(i.rule_id, i.selector, tuple(i.criteria), i.severity) for i in issues}
    assert found == {
        (
            "ramp-link-purpose",
            "#l1",
            ("2.4.4",),
            Severity.SERIOUS,
        ),  # link99 unknown, link2 low conf
        ("ramp-heading-markup", "#s2", ("1.3.1",), Severity.MODERATE),  # s1 named a wrong criterion
    }


def _fake_structure(result: StructureJudgments) -> Any:
    async def judge(evidence: PageEvidence, candidates: list[StructureCandidate]) -> Any:
        valid = {c.cid for c in candidates}
        return {j.cid: j for j in result.items if j.cid in valid}

    return judge
