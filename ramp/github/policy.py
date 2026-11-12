"""Rules for opening pull requests on repositories, especially ones we do not own.

- Our own repositories (owner listed in ``RAMP_OWNED_OWNERS``): allowed.
- Anyone else's: read CONTRIBUTING and any AI-contribution policy first. If the project rejects
  AI-generated contributions, refuse. If it asks for disclosure, add it to the PR body.
- Never more than one Ramp PR per repository (ledger in ``.ramp/pr-ledger.json``) unless the
  maintainer invited more (``invited=True``). Never in bulk.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

POLICY_FILES = [
    "CONTRIBUTING.md",
    ".github/CONTRIBUTING.md",
    "docs/CONTRIBUTING.md",
    "AI_POLICY.md",
    ".github/AI_POLICY.md",
    "AI-POLICY.md",
    "CODE_OF_CONDUCT.md",
]
_PROHIBITS_AI = re.compile(
    r"(do not|don't|never)\s+(submit|open|send)[^.]{0,60}\b(ai|llm|machine)[- ]generated"
    r"|\b(ai|llm|machine)[- ](generated|written|assisted)[^.]{0,80}\b(not (be )?accepted|"
    r"(will be|are) (rejected|closed)|prohibited|not allowed|banned)"
    r"|no (ai|llm)[- ](generated|assisted) (code|contributions|pull requests|prs)",
    re.IGNORECASE,
)
_REQUIRES_DISCLOSURE = re.compile(
    r"(disclose|disclosure|declare|state|mention)[^.]{0,80}\b(ai|llm|generated|assist)",
    re.IGNORECASE,
)
DISCLOSURE = (
    "**AI disclosure.** This pull request was prepared with Ramp, an automated accessibility "
    "auditor that uses language models to propose fixes. A human reviewed and approved the exact "
    "diff before it was submitted."
)


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str
    disclosure_required: bool = False
    files_read: list[str] = field(default_factory=list)


def owned_owners() -> set[str]:
    return {o.strip().lower() for o in os.environ.get("RAMP_OWNED_OWNERS", "").split(",") if o}


def evaluate_policy(owner: str, documents: dict[str, str]) -> PolicyDecision:
    """Decide from the repository's policy documents (path -> text)."""
    files = sorted(documents)
    if owner.lower() in owned_owners():
        return PolicyDecision(True, "repository owned by the operator", files_read=files)
    text = "\n".join(documents.values())
    if _PROHIBITS_AI.search(text):
        return PolicyDecision(
            False, "the project does not accept AI-generated contributions", files_read=files
        )
    if not documents:
        return PolicyDecision(
            True,
            "no contribution policy found; disclosure added by default",
            disclosure_required=True,
            files_read=files,
        )
    # On repositories we do not own, Ramp always discloses, whether or not the policy asks.
    explicit = bool(_REQUIRES_DISCLOSURE.search(text))
    reason = "policy requires AI disclosure" if explicit else "policy read; disclosure by default"
    return PolicyDecision(True, reason, disclosure_required=True, files_read=files)


@dataclass
class PRLedger:
    """One Ramp PR per repository unless invited."""

    path: Path = field(default_factory=lambda: Path(".ramp/pr-ledger.json"))

    def _load(self) -> dict[str, list[dict[str, str]]]:
        if not self.path.exists():
            return {}
        data: dict[str, list[dict[str, str]]] = json.loads(self.path.read_text())
        return data

    def may_open(self, repo: str, invited: bool = False) -> bool:
        return invited or not self._load().get(repo.lower())

    def record(self, repo: str, url: str) -> None:
        data = self._load()
        data.setdefault(repo.lower(), []).append(
            {"url": url, "at": datetime.now(UTC).isoformat(timespec="seconds")}
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2))
