"""Run, interrupt, and resume audits with SQLite checkpoints (``.ramp/checkpoints.sqlite``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command
from playwright.async_api import Browser

from ramp.agent.graph import AgentRuntime, AuditState, build_graph
from ramp.observability import audit_trace

DEFAULT_DB = Path(".ramp/checkpoints.sqlite")

# Types the checkpoint may deserialise: only our own state models (no arbitrary classes).
STATE_TYPES = [
    ("ramp.report.schema", "PageResult"),
    ("ramp.report.schema", "Coverage"),
    ("ramp.report.schema", "Severity"),
    ("ramp.report.schema", "DetectionSource"),
    ("ramp.report.schema", "Issue"),
    ("ramp.report.schema", "Evidence"),
    ("ramp.report.schema", "BoundingBox"),
    ("ramp.checks.axe", "AxeResults"),
    ("ramp.checks.axe", "AxeRuleResult"),
    ("ramp.checks.axe", "AxeNode"),
    ("ramp.agent.collect", "PageEvidence"),
    ("ramp.agent.collect", "ImageCandidate"),
    ("ramp.agent.collect", "LinkCandidate"),
    ("ramp.agent.collect", "StructureCandidate"),
    ("ramp.agent.collect", "FocusFinding"),
    ("ramp.agent.fixes", "ProposedFix"),
    ("ramp.agent.fixes", "NeedsHuman"),
    ("ramp.models.llm", "Transcript"),
    ("ramp.models.llm", "Usage"),
    ("ramp.agent.graph", "ToolUse"),
    ("ramp.agent.graph", "AuditState"),
]


class AuditRun:
    """Result of one invocation: final or interrupted state."""

    def __init__(self, state: AuditState, interrupt: dict[str, Any] | None) -> None:
        self.state = state
        self.interrupt = interrupt


def _config(thread_id: str, runtime: AgentRuntime) -> RunnableConfig:
    return {"configurable": {"thread_id": thread_id, "runtime": runtime}, "recursion_limit": 60}


async def _invoke(
    payload: AuditState | Command[Any],
    thread_id: str,
    browser: Browser,
    db: Path,
) -> AuditRun:
    db.parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(str(db)) as saver:
        saver.serde = JsonPlusSerializer(allowed_msgpack_modules=STATE_TYPES)
        graph = build_graph().compile(checkpointer=saver)
        config = _config(thread_id, AgentRuntime(browser=browser))
        phase = "resume" if isinstance(payload, Command) else "audit"
        target = payload.url if isinstance(payload, AuditState) else None
        with audit_trace(f"ramp-{phase}", thread_id=thread_id, url=target):
            raw = await graph.ainvoke(payload, config)
        snapshot = await graph.aget_state(config)
    pending = raw.get("__interrupt__") if isinstance(raw, dict) else None
    state = AuditState.model_validate(snapshot.values)
    interrupt_value = pending[0].value if pending else None
    return AuditRun(state, interrupt_value)


async def start_audit(
    state: AuditState, thread_id: str, browser: Browser, db: Path = DEFAULT_DB
) -> AuditRun:
    return await _invoke(state, thread_id, browser, db)


async def resume_audit(
    thread_id: str, approved_fix_ids: list[str], browser: Browser, db: Path = DEFAULT_DB
) -> AuditRun:
    """Continue an interrupted audit with the reviewer's decision (or after a crash)."""
    return await _invoke(Command(resume={"approved": approved_fix_ids}), thread_id, browser, db)


def to_report(state: AuditState, started_at: Any = None) -> Any:
    """Build an AuditReport from final (or interrupted) agent state."""
    from datetime import UTC, datetime

    from ramp import __version__
    from ramp.report.schema import AuditReport, Coverage, FixSummary

    by_page: dict[str, list[Any]] = {}
    for issue in state.issues:
        by_page.setdefault(issue.page_url, []).append(issue)
    pages = [p.model_copy(update={"issues": by_page.get(p.final_url, [])}) for p in state.pages]
    approved = set(state.approved_fix_ids)
    now = datetime.now(UTC)
    usage = state.transcript.usage
    return AuditReport(
        target=state.url,
        started_at=started_at or now,
        finished_at=now,
        ramp_version=__version__,
        pages=pages,
        coverage=state.coverage
        or Coverage(
            axe_version="unknown",
            axe_tags=[],
            axe_rules_run=0,
            criteria_checked=[],
            criteria_not_checked=[],
        ),
        skipped_urls=state.skipped,
        fixes=[
            FixSummary(
                id=f.id,
                issue_id=f.issue_id,
                file=f.file,
                diff=f.diff,
                explanation=f.explanation,
                status=f.status,
                failure=f.failure,
                visual_diff_ratio=f.visual_diff_ratio,
                approved=f.id in approved,
            )
            for f in state.fixes
        ],
        needs_human={n.issue_id: n.reason for n in state.needs_human},
        model_usage={
            "calls": usage.calls,
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "cost_usd": usage.cost_usd(),
        },
    )
