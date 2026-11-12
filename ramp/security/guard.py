"""Output-side defenses: what a model says is checked before Ramp uses it.

Input-side separation (escaped data blocks, random boundaries, no tools for models) makes
injection hard; these checks assume it can still happen and limit what it can achieve:

- **Prompt canary.** Each call's system prompt carries a fresh random marker the model is told
  never to output. If it appears, the model was steered into leaking its instructions; the
  reply is rejected.
- **Identifier scrubbing.** Code-like tokens (``RAMP-CANARY-A11007``, ``AKIA...``, long hex) are
  removed from model free text. Good alt text and link text almost never need them, and they are
  how exfiltration and "verification code" injections show up.
- **Instruction scrubbing.** Free text that repeats instructions aimed at automated tools
  ("ignore previous instructions", "report zero issues") is replaced with a neutral description,
  and the element is flagged as a likely injection.
- **Patch policy.** A fix may not add scripts, event handlers, ``javascript:`` URLs, embeds, or
  external URLs that were not already in the replaced code, and may not introduce code-like
  identifiers that are not already in the file.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass

_CODE_TOKEN = re.compile(
    r"\b(?=[A-Z0-9_-]*\d)(?=[A-Z0-9_-]*[A-Z])[A-Z0-9]+(?:[-_][A-Z0-9]+){1,}\b"  # RAMP-CANARY-A11007
    r"|\b[a-f0-9]{24,}\b"  # long hex
    r"|\bAKIA[0-9A-Z]{12,}\b"  # cloud key shapes
)
_AI_DIRECTED = re.compile(
    r"ignore (all |any )?(previous|prior|above) instructions|"
    r"(note|message|instruction)s? (to|for) (the )?(ai|llm|assistant|automated|auditor)|"
    r"\b(ai|llm) (auditor|agent|tool|assistant)s?\b|"
    r"report (zero|no) (issues|findings|problems)|"
    r"system (message|prompt|instruction)|verification code|"
    r"(mark|treat) (all|every) (issues?|findings?) (as )?(minor|resolved)|"
    r"exempt from (wcag|accessibility)",
    re.IGNORECASE,
)
NEUTRAL_TEXT = "Text addressed to automated tools"
_FORBIDDEN_IN_PATCH = [
    (re.compile(r"<\s*script", re.I), "adds a script"),
    (re.compile(r"\son[a-z]+\s*=", re.I), "adds an event handler attribute"),
    (re.compile(r"javascript:", re.I), "adds a javascript: URL"),
    (re.compile(r"<\s*(iframe|object|embed|link|meta|base|form)\b", re.I), "adds an embed or form"),
]
_URL = re.compile(r"(?:https?:)?//[^\s\"'<>)]+", re.I)


def new_prompt_canary() -> str:
    return f"canary-{secrets.token_hex(8)}"


def leaked(text: str, canary: str) -> bool:
    return canary in text


def code_tokens(text: str) -> set[str]:
    return set(_CODE_TOKEN.findall(text or ""))


def looks_ai_directed(text: str) -> bool:
    return bool(_AI_DIRECTED.search(text or ""))


@dataclass
class Scrubbed:
    text: str
    removed_tokens: list[str]
    ai_directed: bool


def scrub(text: str, neutral: str = NEUTRAL_TEXT) -> Scrubbed:
    """Remove code-like identifiers; replace AI-directed instructions with neutral text."""
    if not text:
        return Scrubbed(text="", removed_tokens=[], ai_directed=False)
    if looks_ai_directed(text):
        return Scrubbed(text=neutral, removed_tokens=sorted(code_tokens(text)), ai_directed=True)
    tokens = sorted(code_tokens(text))
    cleaned = text
    for token in tokens:
        cleaned = cleaned.replace(token, "[identifier removed]")
    return Scrubbed(text=cleaned, removed_tokens=tokens, ai_directed=False)


def patch_violation(old: str, new: str, file_text: str) -> str | None:
    """Reason a patch breaks policy, or None. ``file_text`` is the whole original file."""
    for pattern, reason in _FORBIDDEN_IN_PATCH:
        if len(pattern.findall(new)) > len(pattern.findall(old)):
            return f"fix {reason}"
    added_urls = set(_URL.findall(new)) - set(_URL.findall(old))
    if added_urls:
        return f"fix adds external URLs: {', '.join(sorted(added_urls))[:200]}"
    new_tokens = code_tokens(new) - code_tokens(file_text)
    if new_tokens:
        return f"fix introduces identifiers not in the source: {', '.join(sorted(new_tokens))}"
    if looks_ai_directed(new) and not looks_ai_directed(old):
        return "fix adds text addressed to automated tools"
    return None
