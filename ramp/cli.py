"""Command-line entry point: ``ramp``."""

from __future__ import annotations

import typer

from ramp import __version__

app = typer.Typer(help="Ramp: agentic accessibility auditor.", no_args_is_help=True)


@app.command()
def version() -> None:
    """Print the installed version."""
    typer.echo(__version__)


@app.command()
def audit(url: str) -> None:
    """Audit a URL (implemented in Phase 1)."""
    typer.echo(f"audit is not implemented yet (Phase 1): {url}")
    raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
