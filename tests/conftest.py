"""Shared fixtures: a local static server for the fixture site and a fixture source repo."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from ramp.evals.static_server import StaticServer

FIXTURES = Path(__file__).parent / "fixtures"

__all__ = ["FIXTURES", "StaticServer"]


@pytest.fixture
def fixture_site() -> Iterator[StaticServer]:
    with StaticServer(FIXTURES / "site") as server:
        yield server


@pytest.fixture
def fixture_repo() -> Path:
    return FIXTURES / "repo"
