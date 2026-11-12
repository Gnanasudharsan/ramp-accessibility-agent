"""Phase 0 smoke tests: package imports, settings defaults, API health, CLI."""

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from ramp import __version__
from ramp.api.app import app as api
from ramp.cli import app as cli
from ramp.config import Settings


def test_settings_enforce_polite_crawling() -> None:
    settings = Settings()
    assert settings.min_seconds_between_requests >= 1.0
    assert "RampA11yBot" in settings.user_agent


def test_settings_reject_faster_than_one_request_per_second() -> None:
    import pydantic

    try:
        Settings(min_seconds_between_requests=0.2)
    except pydantic.ValidationError:
        return
    raise AssertionError("rate limit below 1 req/s must be rejected")


def test_healthz() -> None:
    response = TestClient(api).get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_cli_version() -> None:
    result = CliRunner().invoke(cli, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout
