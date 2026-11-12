"""Versioned prompts: each file starts with ``version: N``; evals record name, version, hash."""

from __future__ import annotations

import hashlib
from functools import cache
from pathlib import Path

_DIR = Path(__file__).parent


@cache
def load(name: str) -> str:
    text = (_DIR / f"{name}.md").read_text(encoding="utf-8")
    return text.split("\n", 1)[1].strip() if text.startswith("version:") else text.strip()


@cache
def fingerprint(name: str) -> str:
    raw = (_DIR / f"{name}.md").read_text(encoding="utf-8")
    version = raw.split("\n", 1)[0].removeprefix("version:").strip()
    return f"{name}@v{version}#{hashlib.sha256(raw.encode()).hexdigest()[:8]}"


def all_fingerprints() -> list[str]:
    return sorted(fingerprint(p.stem) for p in _DIR.glob("*.md"))
