"""Judgment-based checks: image alternatives, link purpose, and visual structure.

The model judges; this module decides what becomes an issue. Model output is validated three
ways before it can create an issue:
1. it must parse into the Pydantic schema (``StructuredLLM`` retries on violations),
2. it may only refer to candidate ids we sent (anything else is dropped), and
3. the WCAG criterion and severity come from fixed tables here, never from the model, so page
   text cannot talk the system into a different criterion or a lower severity.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from ramp.agent import prompts
from ramp.agent.collect import ImageCandidate, LinkCandidate, PageEvidence, StructureCandidate
from ramp.models.llm import LLMError, StructuredLLM, image_part, untrusted_block
from ramp.report.schema import DetectionSource, Evidence, Issue, Severity
from ramp.security.guard import scrub

log = logging.getLogger(__name__)

ImageProblem = Literal[
    "none",
    "missing",
    "filename",
    "generic",
    "wrong_description",
    "decorative_needs_empty",
    "text_not_conveyed",
    "missing_data",
]


class ImageJudgment(BaseModel):
    decorative: bool
    contains_text: bool
    visible_text: str = Field(default="", max_length=400)
    problem: ImageProblem
    suggested_alt: str = Field(default="", max_length=300)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(default="", max_length=400)


class LinkJudgment(BaseModel):
    cid: str
    purpose_clear: bool
    problem: Literal["none", "ambiguous", "filename_or_code", "instruction_not_purpose", "empty"]
    suggested_text: str = Field(default="", max_length=200)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(default="", max_length=400)


class LinkJudgments(BaseModel):
    items: list[LinkJudgment]


class StructureJudgment(BaseModel):
    cid: str
    is_barrier: bool
    criterion: str
    problem: str = Field(default="", max_length=200)
    suggested_fix: str = Field(default="", max_length=300)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(default="", max_length=400)


class StructureJudgments(BaseModel):
    items: list[StructureJudgment]


# Fixed mapping from finding type to WCAG criteria, severity, and title.
IMAGE_RULES: dict[str, tuple[str, list[str], Severity, str]] = {
    "missing": (
        "ramp-image-alt-quality",
        ["1.1.1"],
        Severity.CRITICAL,
        "Informative image has no text alternative",
    ),
    "filename": (
        "ramp-image-alt-quality",
        ["1.1.1"],
        Severity.SERIOUS,
        "Image alt text is a file name",
    ),
    "generic": (
        "ramp-image-alt-quality",
        ["1.1.1"],
        Severity.SERIOUS,
        "Image alt text is a generic placeholder",
    ),
    "wrong_description": (
        "ramp-image-alt-quality",
        ["1.1.1"],
        Severity.SERIOUS,
        "Image alt text does not describe the image",
    ),
    "missing_data": (
        "ramp-image-alt-quality",
        ["1.1.1"],
        Severity.SERIOUS,
        "Chart or diagram alt text omits its information",
    ),
    "decorative_needs_empty": (
        "ramp-decorative-alt",
        ["1.1.1"],
        Severity.MINOR,
        "Decorative image should have empty alt text",
    ),
    "text_not_conveyed": (
        "ramp-image-of-text",
        ["1.4.5", "1.1.1"],
        Severity.SERIOUS,
        "Image of text whose text is not conveyed",
    ),
}
STRUCTURE_RULES: dict[str, dict[str, tuple[str, Severity, str]]] = {
    "heading_like": {
        "1.3.1": (
            "ramp-heading-markup",
            Severity.MODERATE,
            "Visual heading is not marked up as a heading",
        )
    },
    "table": {
        "1.3.1": ("ramp-table-headers", Severity.SERIOUS, "Data table headers are not marked up")
    },
    "instructions": {
        "1.3.3": (
            "ramp-sensory-instructions",
            Severity.MODERATE,
            "Instructions rely on sensory characteristics",
        )
    },
    "form": {"1.4.1": ("ramp-color-only", Severity.SERIOUS, "Information conveyed by color alone")},
    "media": {
        "1.2.2": ("ramp-media-captions", Severity.CRITICAL, "Video has no captions"),
        "1.2.1": ("ramp-media-transcript", Severity.SERIOUS, "Audio has no transcript"),
    },
}
LINK_RULE = ("ramp-link-purpose", ["2.4.4"], Severity.SERIOUS, "Link purpose is unclear")
FOCUS_RULE = ("ramp-focus-visible", ["2.4.7"], Severity.SERIOUS, "No visible focus indicator")


INJECTION_NOTE = (
    "This element contains text addressed to automated tools (possible prompt injection); "
    "Ramp treated it as data."
)


def _issue(
    page_url: str,
    rule: str,
    criteria: list[str],
    severity: Severity,
    title: str,
    selector: str,
    html: str,
    summary: str,
    confidence: float,
    source: DetectionSource,
    suggestion: str = "",
) -> Issue:
    clean_summary, clean_suggestion = scrub(summary), scrub(suggestion)
    summary = clean_summary.text
    if clean_summary.ai_directed or clean_suggestion.ai_directed:
        summary = f"{summary} {INJECTION_NOTE}".strip()
    suggestion = "" if clean_suggestion.ai_directed else clean_suggestion.text
    return Issue(
        id=Issue.make_id(page_url, rule, selector),
        rule_id=rule,
        title=title,
        criteria=criteria,
        severity=severity,
        page_url=page_url,
        selector=selector,
        element_key=selector,
        evidence=Evidence(html_snippet=html[:4000], failure_summary=summary[:1000]),
        source=source,
        confidence=round(confidence, 3),
        suggested_fix=suggestion[:300] or None,
    )


class VisionChecker:
    def __init__(
        self, vision: StructuredLLM, text: StructuredLLM, out_dir: Path, min_confidence: float
    ) -> None:
        self.vision, self.text, self.out_dir = vision, text, out_dir
        self.min_confidence = min_confidence
        self.system_preamble = prompts.load("preamble")

    def _system(self, name: str) -> str:
        return f"{self.system_preamble}\n\n{prompts.load(name)}"

    async def judge_image(self, image: ImageCandidate) -> ImageJudgment | None:
        if image.crop_path is None:
            return None
        crop = (self.out_dir / image.crop_path).read_bytes()
        data = {
            "alt": image.alt,
            "in_link": image.in_link,
            "link_href": image.link_href,
            "link_other_text": image.link_text,
            "file_name": image.src_file,
            "nearby_text": image.nearby_text,
        }
        user = [
            {"type": "text", "text": "Judge this image.\n" + untrusted_block("page_data", data)},
            image_part(crop),
        ]
        try:
            return await self.vision.complete(
                system=self._system("image_alt"), user=user, schema=ImageJudgment, max_tokens=500
            )
        except LLMError as exc:
            log.warning("image judgment failed: %s", exc)
            return None

    async def judge_links(self, links: list[LinkCandidate]) -> dict[str, LinkJudgment]:
        if not links:
            return {}
        data = [
            {
                "cid": x.cid,
                "name": x.name,
                "href": x.href,
                "context": x.context,
                "preceding_heading": x.heading,
                "same_name_other_targets": x.same_name_other_targets,
            }
            for x in links
        ]
        try:
            result = await self.text.complete(
                system=self._system("link_purpose"),
                user="Judge these links.\n" + untrusted_block("page_data", data),
                schema=LinkJudgments,
                max_tokens=400 + 120 * len(links),
            )
        except LLMError as exc:
            log.warning("link judgment failed: %s", exc)
            return {}
        valid = {x.cid for x in links}
        return {j.cid: j for j in result.items if j.cid in valid}

    async def judge_structure(
        self, evidence: PageEvidence, candidates: list[StructureCandidate]
    ) -> dict[str, StructureJudgment]:
        if not candidates or evidence.screenshot_path is None:
            return {}
        data = [
            {"cid": c.cid, "kind": c.kind, "text": c.text, "html": c.html, "details": c.details}
            for c in candidates
        ]
        prompt = "Review these candidates.\n" + untrusted_block("page_data", data)
        screenshot = (self.out_dir / evidence.screenshot_path).read_bytes()
        user = [{"type": "text", "text": prompt}, image_part(screenshot, max_side=1024)]
        try:
            result = await self.vision.complete(
                system=self._system("structure"),
                user=user,
                schema=StructureJudgments,
                max_tokens=200 + 160 * len(candidates),
            )
        except LLMError as exc:
            log.warning("structure judgment failed: %s", exc)
            return {}
        valid = {c.cid for c in candidates}
        return {j.cid: j for j in result.items if j.cid in valid}

    async def recheck_element(self, evidence: PageEvidence, issue: Issue) -> bool:
        """Re-judge only the element an issue was about. True if it is still a barrier.

        Used by fix verification: re-running every check on the page would spend the token
        budget on elements the fix did not touch.
        """
        key = issue.element_key or issue.selector
        snippet = issue.evidence.html_snippet[:60]
        if issue.rule_id in {"ramp-image-alt-quality", "ramp-decorative-alt", "ramp-image-of-text"}:
            image = next((i for i in evidence.images if i.selector == key), None)
            image = image or next((i for i in evidence.images if i.html[:60] == snippet), None)
            if image is None:
                return False
            verdict = await self.judge_image(image)
            return verdict is not None and verdict.problem != "none"
        if issue.rule_id == "ramp-link-purpose":
            link = next((x for x in evidence.links if x.selector == key), None)
            if link is None:
                return False
            link_verdict = (await self.judge_links([link])).get(link.cid)
            return link_verdict is not None and not link_verdict.purpose_clear
        if issue.rule_id == "ramp-focus-visible":
            return any(f.selector == key for f in evidence.focus_without_indicator)
        candidate = next((c for c in evidence.structure if c.selector == key), None)
        if candidate is None:
            return False  # no longer looks like the problem (e.g. now a real heading)
        structure_verdict = (await self.judge_structure(evidence, [candidate])).get(candidate.cid)
        return structure_verdict is not None and structure_verdict.is_barrier

    async def check_page(self, evidence: PageEvidence, page_url: str) -> list[Issue]:
        issues: list[Issue] = []
        vision_src = DetectionSource.VISION

        for image in evidence.images:
            verdict = await self.judge_image(image)
            if verdict is None or verdict.problem == "none":
                continue
            if verdict.confidence < self.min_confidence:
                continue
            problem = verdict.problem
            if problem == "text_not_conveyed" and image.in_link and not image.link_text:
                problem = "wrong_description"
            rule, criteria, severity, title = IMAGE_RULES[problem]
            if image.in_link and not image.link_text and problem != "decorative_needs_empty":
                criteria = [*criteria, "2.4.4"]
            issues.append(
                _issue(
                    page_url,
                    rule,
                    criteria,
                    severity,
                    title,
                    image.selector,
                    image.html,
                    verdict.reason,
                    verdict.confidence,
                    vision_src,
                    suggestion=f'alt="{verdict.suggested_alt}"',
                )
            )

        links = [x for x in evidence.links if not x.href.startswith("#")]
        for cid, link_verdict in (await self.judge_links(links)).items():
            if link_verdict.purpose_clear or link_verdict.problem == "none":
                continue
            if link_verdict.confidence < self.min_confidence:
                continue
            link = next(x for x in links if x.cid == cid)
            rule, criteria, severity, title = LINK_RULE
            better = link_verdict.suggested_text
            issues.append(
                _issue(
                    page_url,
                    rule,
                    criteria,
                    severity,
                    title,
                    link.selector,
                    link.html,
                    link_verdict.reason,
                    link_verdict.confidence,
                    vision_src,
                    suggestion=f"Link text: {better}" if better else "",
                )
            )

        structure = await self.judge_structure(evidence, evidence.structure)
        for candidate in evidence.structure:
            judgment = structure.get(candidate.cid)
            if judgment is None or not judgment.is_barrier:
                continue
            if judgment.confidence < self.min_confidence:
                continue
            allowed = STRUCTURE_RULES.get(candidate.kind, {})
            if judgment.criterion not in allowed:
                continue  # model named a criterion this kind of candidate cannot fail
            rule, severity, title = allowed[judgment.criterion]
            issues.append(
                _issue(
                    page_url,
                    rule,
                    [judgment.criterion],
                    severity,
                    title,
                    candidate.selector,
                    candidate.html,
                    judgment.reason,
                    judgment.confidence,
                    vision_src,
                    suggestion=judgment.suggested_fix,
                )
            )

        for focus in evidence.focus_without_indicator:
            rule, criteria, severity, title = FOCUS_RULE
            issues.append(
                _issue(
                    page_url,
                    rule,
                    criteria,
                    severity,
                    title,
                    focus.selector,
                    focus.html,
                    "Focused and unfocused screenshots are pixel-identical.",
                    1.0,
                    DetectionSource.RULE,
                    suggestion="Add a visible :focus-visible style.",
                )
            )
        return issues
