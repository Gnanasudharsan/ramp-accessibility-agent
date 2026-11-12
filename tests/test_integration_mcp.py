"""ramp-a11y-mcp exercised through real MCP clients: in-process and over stdio."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from ramp.mcp_server.server import mcp
from tests.conftest import StaticServer

pytestmark = pytest.mark.integration


def _structured(result: Any) -> dict[str, Any]:
    assert not result.is_error, result.content
    data: dict[str, Any] = result.structured_content
    return data


async def test_lists_the_four_tools_as_read_only() -> None:
    async with Client(mcp) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == {"run_axe", "contrast_check", "focus_order", "map_to_source"}
    assert all(t.annotations and t.annotations.read_only_hint for t in tools.values())


async def test_tools_end_to_end(
    fixture_site: StaticServer, fixture_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RAMP_MCP_SOURCE_ROOTS", str(fixture_repo))
    url = f"{fixture_site.url}/index.html"
    async with Client(mcp) as client:
        axe = _structured(await client.call_tool("run_axe", {"url": url}))
        faint = _structured(
            await client.call_tool("contrast_check", {"url": url, "selector": "#faint"})
        )
        ok = _structured(await client.call_tool("contrast_check", {"url": url, "selector": "#ok"}))
        glass = _structured(
            await client.call_tool("contrast_check", {"url": url, "selector": "#on-glass"})
        )
        focus = _structured(await client.call_tool("focus_order", {"url": url}))
        source = _structured(
            await client.call_tool(
                "map_to_source",
                {"selector": "#hero", "repo_path": str(fixture_repo), "url": url},
            )
        )
        denied = await client.call_tool(
            "map_to_source", {"selector": "#hero", "repo_path": "/etc", "html_snippet": "<img>"}
        )
        robots = await client.call_tool("run_axe", {"url": f"{fixture_site.url}/private/x.html"})

    rules = {v["rule_id"] for v in axe["violations"]}
    assert {"image-alt", "color-contrast"} <= rules
    assert faint["passes"] is False
    assert faint["ratio"] == pytest.approx(2.32, abs=0.01)  # #aaa on white
    assert ok["passes"] is True
    assert glass["background"] == "rgb(128, 128, 128)"  # 50% black composited on white
    names = [s["name"] for s in focus["stops"]]
    assert names[:2] == ["Page two", "Private"]
    nofocus = next(s for s in focus["stops"] if s["name"] == "Private")
    assert nofocus["indicator_visible"] is False  # a:focus { outline: none }
    assert focus["stops"][0]["indicator_visible"] is True
    assert source["candidates"][0]["path"] == "src/Hero.jsx"
    assert denied.is_error
    assert robots.is_error


async def test_server_works_over_stdio(fixture_site: StaticServer) -> None:
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "ramp.mcp_server.server"], cwd=str(Path.cwd())
    )
    async with Client(params) as client:
        result = await client.call_tool("run_axe", {"url": f"{fixture_site.url}/page3.html"})
    data = _structured(result)
    assert data["axe_version"] == "4.14.0"
