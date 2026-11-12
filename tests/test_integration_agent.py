"""The agent graph end to end with fake models: interrupt for review, resume from checkpoint."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from ramp.agent import graph as graph_module
from ramp.agent.fixes import FixProposalLLM
from ramp.agent.graph import AuditState
from ramp.agent.run import resume_audit, start_audit, to_report
from ramp.agent.vision import ImageJudgment, LinkJudgments, StructureJudgments
from ramp.audit import launch_browser
from ramp.evals.static_server import StaticServer
from ramp.models.llm import Transcript
from tests.conftest import FIXTURES

pytestmark = pytest.mark.integration

HERO_OLD = '<img id="hero" src="hero.png">'
HERO_NEW = '<img id="hero" src="hero.png" alt="Library entrance">'


class FakeLLM:
    def __init__(self, transcript: Transcript) -> None:
        self.transcript = transcript

    async def complete(self, *, system: str, user: Any, schema: type[BaseModel]) -> BaseModel:
        self.transcript.usage.calls += 1
        if schema is ImageJudgment:
            reply: BaseModel = ImageJudgment(
                decorative=False, contains_text=False, problem="none", confidence=0.9
            )
        elif schema is LinkJudgments:
            reply = LinkJudgments(items=[])
        elif schema is StructureJudgments:
            reply = StructureJudgments(items=[])
        elif schema is FixProposalLLM:
            reply = FixProposalLLM(old=HERO_OLD, new=HERO_NEW, explanation="Adds alt (1.1.1).")
        else:
            raise AssertionError(schema)
        self.transcript.outputs.append(reply.model_dump_json())
        return reply


def _fake_bind(self: Any, state: AuditState) -> tuple[Any, Any]:
    self.transcript = state.transcript.model_copy(deep=True)
    return FakeLLM(self.transcript), FakeLLM(self.transcript)


async def test_interrupt_then_resume_writes_only_approved_verified_diffs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(graph_module.AgentRuntime, "bind", _fake_bind)
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURES / "site", repo)
    db = tmp_path / "ckpt.sqlite"
    with StaticServer(repo) as server:
        state = AuditState(
            url=f"{server.url}/index.html",
            out_dir=str(tmp_path / "out"),
            repo_path=str(repo),
            max_pages=1,
            max_depth=0,
            offline=True,
            review_mode="interrupt",
            max_fixes=3,
        )
        async with launch_browser() as browser:
            first = await start_audit(state, "t1", browser, db=db)
            assert first.interrupt is not None
            offered = [f["id"] for f in first.interrupt["fixes"]]
            hero_fix = next(
                f for f in first.state.fixes if f.new == HERO_NEW and f.status == "verified"
            )
            assert hero_fix.id in offered
            assert all(f.status in {"verified", "failed"} for f in first.state.fixes)
            # The repo is untouched until approval.
            assert HERO_NEW not in (repo / "index.html").read_text()

            resumed = await resume_audit("t1", [hero_fix.id], browser, db=db)

    assert resumed.interrupt is None
    assert resumed.state.approved_fix_ids == [hero_fix.id]
    assert resumed.state.pr is not None
    patch = Path(resumed.state.pr["patch"]).read_text()
    assert f"+{HERO_NEW}" in patch.replace("  ", "") or HERO_NEW in patch
    report = to_report(resumed.state)
    assert any(f.approved for f in report.fixes)
    assert {"image-alt"} <= {i.rule_id for i in report.issues}
    # Every tool use stayed inside its node's allowlist.
    assert all(u.allowed for u in resumed.state.tool_uses)
