"""Command-line entry point: ``ramp``."""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Annotated
from urllib.parse import urlsplit

import typer
from rich.console import Console
from rich.table import Table

from ramp import __version__
from ramp.config import get_settings

if TYPE_CHECKING:
    from playwright.async_api import Browser

    from ramp.agent.run import AuditRun

app = typer.Typer(help="Ramp: agentic accessibility auditor.", no_args_is_help=True)
console = Console()


def _default_out_dir(url: str) -> Path:
    host = urlsplit(url).netloc or "target"
    return Path("reports") / re.sub(r"[^A-Za-z0-9.-]+", "_", host)


@app.command()
def version() -> None:
    """Print the installed version."""
    typer.echo(__version__)


@app.command()
def audit(
    url: str,
    out: Annotated[
        Path | None, typer.Option(help="Output directory (default reports/<host>).")
    ] = None,
    max_pages: Annotated[int | None, typer.Option(min=1, max=200, help="Page cap.")] = None,
    max_depth: Annotated[int | None, typer.Option(min=0, max=5, help="Link depth.")] = None,
) -> None:
    """Crawl URL, run axe-core on each page, and write report.json + report.html."""
    from ramp.audit import audit_url
    from ramp.report.html import write_reports

    settings = get_settings()
    out_dir = out or _default_out_dir(url)
    report = asyncio.run(
        audit_url(
            url,
            out_dir,
            user_agent=settings.user_agent,
            max_pages=max_pages or settings.max_pages,
            max_depth=max_depth if max_depth is not None else settings.max_depth,
        )
    )
    json_path, html_path = write_reports(report, out_dir)

    table = Table(title=f"Ramp audit — {url}")
    table.add_column("Page")
    table.add_column("Issues", justify="right")
    table.add_column("Needs review", justify="right")
    for page in report.pages:
        table.add_row(page.final_url, str(len(page.issues)), str(page.needs_review))
    console.print(table)
    console.print(f"[bold]{len(report.issues)}[/bold] issues · JSON {json_path} · HTML {html_path}")
    console.print(f"[dim]{report.disclaimer}[/dim]")


@app.command()
def agent(
    url: str,
    repo: Annotated[
        Path | None, typer.Option(help="Source repo (static site root) to patch.")
    ] = None,
    out: Annotated[Path | None, typer.Option(help="Output directory.")] = None,
    max_pages: Annotated[int, typer.Option(min=1, max=200)] = 5,
    max_depth: Annotated[int, typer.Option(min=0, max=5)] = 1,
    thread: Annotated[str | None, typer.Option(help="Checkpoint thread id (to resume).")] = None,
    review: Annotated[str, typer.Option(help="interrupt | auto_reject")] = "interrupt",
) -> None:
    """Run the full agent: rule + vision checks, verified fixes, then wait for your approval."""
    from ramp.agent.graph import AuditState

    out_dir = out or _default_out_dir(url)
    thread_id = thread or f"audit-{uuid.uuid4().hex[:8]}"
    state = AuditState(
        url=url,
        out_dir=str(out_dir),
        repo_path=str(repo.resolve()) if repo else None,
        max_pages=max_pages,
        max_depth=max_depth,
        review_mode="auto_reject" if review == "auto_reject" else "interrupt",
    )
    from ramp.agent.run import start_audit

    _run_agent(lambda browser: start_audit(state, thread_id, browser), out_dir, thread_id)


@app.command()
def approve(
    thread: str,
    fix: Annotated[list[str] | None, typer.Option(help="Fix id to approve (repeatable).")] = None,
    all_verified: Annotated[
        bool, typer.Option("--all", help="Approve every verified fix.")
    ] = False,
    out: Annotated[Path | None, typer.Option(help="Output directory used for the audit.")] = None,
) -> None:
    """Approve exact diffs of an interrupted audit and resume it."""
    ids = list(fix or [])
    if all_verified:
        ids = ["*"]
    from ramp.agent.run import resume_audit

    _run_agent(lambda browser: resume_audit(thread, ids, browser), out, thread)


def _run_agent(
    step: Callable[[Browser], Awaitable[AuditRun]], out_dir: Path | None, thread_id: str
) -> None:
    from ramp.agent.run import to_report
    from ramp.audit import launch_browser
    from ramp.report.html import write_reports

    async def go() -> AuditRun:
        async with launch_browser() as browser:
            return await step(browser)

    run = asyncio.run(go())
    directory = out_dir or Path(run.state.out_dir)
    json_path, html_path = write_reports(to_report(run.state), directory)
    console.print(f"[bold]{len(run.state.issues)}[/bold] issues · report {html_path}")
    verified = [f for f in run.state.fixes if f.status == "verified"]
    console.print(f"{len(verified)} verified fixes · {len(run.state.needs_human)} need a human")
    if run.interrupt is not None:
        for f in verified:
            console.print(f"\n[bold]{f.id}[/bold] {f.file}\n{f.explanation}\n{f.diff}")
        console.print(
            f"\nWaiting for approval. Approve with: ramp approve {thread_id} --fix <id> (or --all)"
        )
    elif run.state.pr:
        console.print(f"Result: {run.state.pr}")
    console.print(f"[dim]{json_path}[/dim]")


@app.command("mcp-server")
def mcp_server() -> None:
    """Run the ramp-a11y-mcp server over stdio."""
    from ramp.mcp_server.server import main

    main()


if __name__ == "__main__":
    app()
