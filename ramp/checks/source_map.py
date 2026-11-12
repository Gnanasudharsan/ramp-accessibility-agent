"""Map a rendered DOM element back to the source file and line that most likely produced it.

Deterministic and explainable: parse the element's opening tag, derive "needles" from its most
distinctive attributes (id > src/href/name > alt/aria-label > classes > text), then score
source lines that contain the same tag and those needles. JSX ``className`` is handled.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

SOURCE_EXTENSIONS = frozenset(
    {
        ".html",
        ".htm",
        ".jsx",
        ".tsx",
        ".js",
        ".ts",
        ".vue",
        ".svelte",
        ".astro",
        ".njk",
        ".liquid",
        ".hbs",
        ".erb",
        ".php",
        ".jinja",
        ".j2",
        ".mdx",
    }
)
SKIP_DIRS = frozenset(
    {".git", "node_modules", "dist", "build", ".next", "out", ".venv", "vendor", "coverage"}
)
MAX_FILE_BYTES = 1_000_000

WEIGHTS = {
    "id": 6.0,
    "src": 4.0,
    "href": 3.0,
    "name": 3.0,
    "for": 3.0,
    "alt": 3.0,
    "aria-label": 3.0,
    "class": 1.0,
    "text": 2.0,
    "tag": 1.0,
}


@dataclass
class ElementSignature:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    text: str = ""


class _FirstTag(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.signature: ElementSignature | None = None
        self._depth = 0
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.signature is None:
            self.signature = ElementSignature(tag=tag, attrs={k: v or "" for k, v in attrs})
        self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self.signature is not None:
            self._text.append(data)

    def text(self) -> str:
        return " ".join(" ".join(self._text).split())


def parse_signature(html_snippet: str) -> ElementSignature | None:
    parser = _FirstTag()
    parser.feed(html_snippet)
    if parser.signature is not None:
        parser.signature.text = parser.text()[:80]
    return parser.signature


def _needles(sig: ElementSignature) -> list[tuple[str, str]]:
    needles: list[tuple[str, str]] = []
    for attr in ("id", "src", "href", "name", "for", "alt", "aria-label"):
        value = sig.attrs.get(attr, "").strip()
        if not value:
            continue
        if attr in ("src", "href"):
            value = value.split("?")[0].rstrip("/").rsplit("/", 1)[-1] or value
        needles.append((attr, value))
    for cls in sig.attrs.get("class", "").split()[:3]:
        needles.append(("class", cls))
    if sig.text and len(sig.text) >= 4:
        needles.append(("text", sig.text[:40]))
    return needles


@dataclass(frozen=True)
class SourceCandidate:
    path: str  # relative to repo root
    line: int  # 1-based line of the opening tag
    score: float
    matched: tuple[str, ...]
    excerpt: str


def _iter_source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            path = Path(dirpath) / name
            if path.suffix.lower() in SOURCE_EXTENSIONS and path.stat().st_size <= MAX_FILE_BYTES:
                files.append(path)
    return sorted(files)


_ATTR_EXACT = frozenset({"id", "name", "for"})
PREFERRED_FILE_BONUS = 10.0


def _needle_in(kind: str, value: str, window: str) -> bool:
    """Identifier attributes must match as attributes (``id="hero"``), not as substrings, so
    ``id="reading-room"`` does not match ``src="reading-room.png"``."""
    if kind in _ATTR_EXACT:
        pattern = rf"""\b{re.escape(kind)}\s*=\s*["'{{]?{re.escape(value)}["'}}\s/>]"""
        return re.search(pattern, window) is not None
    return value in window


def map_to_source(
    html_snippet: str, repo_path: Path, top_k: int = 5, prefer_file: str | None = None
) -> list[SourceCandidate]:
    """Rank source locations for the element described by ``html_snippet``.

    ``prefer_file`` (relative to ``repo_path``) is the file known to render the page, for example
    the static file served at the audited URL; its candidates win ties against other files.
    """
    sig = parse_signature(html_snippet)
    if sig is None:
        return []
    needles = _needles(sig)
    tag_re = re.compile(rf"<{re.escape(sig.tag)}\b", re.IGNORECASE)
    root = repo_path.resolve()
    candidates: list[SourceCandidate] = []
    for path in _iter_source_files(root):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for idx, line in enumerate(lines):
            if not tag_re.search(line):
                continue
            window = "\n".join(lines[idx : idx + 6])  # opening tags often span lines
            score, matched = WEIGHTS["tag"], ["tag"]
            for kind, value in needles:
                if _needle_in(kind, value, window):
                    score += WEIGHTS[kind]
                    matched.append(kind)
            relative = str(path.relative_to(root))
            distinctive = len(matched) > 1 or not needles  # bare tags like <html> have no needles
            if prefer_file is not None and relative == prefer_file and distinctive:
                score += PREFERRED_FILE_BONUS
                matched.append("served_file")
            if len(matched) > 1 or not needles:
                candidates.append(
                    SourceCandidate(
                        path=relative,
                        line=idx + 1,
                        score=score,
                        matched=tuple(matched),
                        excerpt=line.strip()[:200],
                    )
                )
    candidates.sort(key=lambda c: (-c.score, c.path, c.line))
    return candidates[:top_k]
