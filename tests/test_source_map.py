from pathlib import Path

import pytest

from ramp.checks.source_map import map_to_source, parse_signature
from ramp.mcp_server.server import ToolError, resolve_repo_path


def test_parse_signature() -> None:
    sig = parse_signature('<a href="/pricing" class="cta big">Pricing <b>now</b></a>')
    assert sig is not None
    assert sig.tag == "a"
    assert sig.attrs["href"] == "/pricing"
    assert sig.text == "Pricing now"


def test_maps_rendered_img_to_jsx_by_id_and_src(fixture_repo: Path) -> None:
    rendered = '<img id="hero" src="https://cdn.example.org/static/hero.png?v=3">'
    best = map_to_source(rendered, fixture_repo)[0]
    assert best.path == "src/Hero.jsx"
    assert best.line == 4
    assert {"id", "src"} <= set(best.matched)


def test_class_attribute_matches_html_source(fixture_repo: Path) -> None:
    best = map_to_source('<a href="/pricing" class="cta">Pricing</a>', fixture_repo)[0]
    assert best.path == "src/index.html"
    assert best.line == 5


def test_no_tag_match_returns_empty(fixture_repo: Path) -> None:
    assert map_to_source('<video src="x.mp4"></video>', fixture_repo) == []


def test_repo_path_must_be_inside_allowed_roots(
    fixture_repo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("RAMP_MCP_SOURCE_ROOTS", str(fixture_repo))
    assert resolve_repo_path(str(fixture_repo / "src")) == (fixture_repo / "src").resolve()
    with pytest.raises(ToolError, match="outside"):
        resolve_repo_path(str(tmp_path))
    with pytest.raises(ToolError, match="outside"):
        resolve_repo_path(str(fixture_repo / ".." / ".."))


def test_id_matches_as_attribute_not_substring(tmp_path: Path) -> None:
    (tmp_path / "a.html").write_text('<img id="other" src="reading-room.png">\n')
    (tmp_path / "b.html").write_text('<img id="reading-room" src="reading-room.png">\n')
    best = map_to_source('<img id="reading-room" src="reading-room.png">', tmp_path)[0]
    assert best.path == "b.html"


def test_preferred_file_wins_ties(tmp_path: Path) -> None:
    for name in ("a.html", "b.html"):
        (tmp_path / name).write_text('<img src="shared.png">\n')
    best = map_to_source('<img src="shared.png">', tmp_path, prefer_file="b.html")[0]
    assert best.path == "b.html"
    assert "served_file" in best.matched
