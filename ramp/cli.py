"""Command-line entry point: ``ramp``."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

import typer
from rich.console import Console
from rich.table import Table

from ramp import __version__
from ramp.config import get_settings

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


@app.command("mcp-server")
def mcp_server() -> None:
    """Run the ramp-a11y-mcp server over stdio."""
    from ramp.mcp_server.server import main

    main()


if __name__ == "__main__":
    app()
