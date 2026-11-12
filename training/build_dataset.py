"""Build the distillation dataset for Ramp's alt-text judge (Phase 5).

Steps (each resumable; outputs under ``training/data/``, which is gitignored):

1. ``fetch``: sample openly licensed photos from Wikimedia Commons (random file namespace,
   JPEG/PNG only), politely (Ramp's User-Agent, one request per second). Each image keeps its
   license, author, and source URL in ``manifest.jsonl``. Only licenses in ``ALLOWED_LICENSES``
   are kept.
2. ``variants``: for every image, four alt-text candidates whose *intended* label is known by
   construction: a real description (from the Commons description), a camera-style file name,
   a generic placeholder, and the description of a different image.
3. ``teacher``: the large vision model judges all four candidates for an image in one call
   (``ImageJudgment`` per candidate, same prompt family as the agent).
4. ``filter``: keep a candidate only if the teacher's verdict agrees with its constructed label
   (agreement check). Disagreements go to ``review_queue.jsonl`` for the human labeling UI.
5. ``split``: train/valid/test by image (no image appears in two splits), written in the chat
   format mlx-vlm's LoRA trainer reads.

Usage: ``uv run python training/build_dataset.py all --images 250``
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import random
import re
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from ramp.agent import prompts
from ramp.config import get_settings
from ramp.crawler.politeness import RateLimiter
from ramp.models.llm import LLMError, StructuredLLM, Transcript, image_part, untrusted_block

DATA = Path(__file__).parent / "data"
IMAGES = DATA / "images"
API = "https://commons.wikimedia.org/w/api.php"
ALLOWED_LICENSES = re.compile(r"^(CC0|CC BY(-SA)? [1-4]\.0|Public domain|PD)", re.IGNORECASE)
GENERIC = ["image", "photo", "picture", "graphic", "img", "banner", "photograph"]
SEED = 1403

Intended = Literal["none", "filename", "generic", "wrong_description"]


class Candidate(BaseModel):
    cid: str
    alt: str
    intended: Intended


class Record(BaseModel):
    image_id: str
    file: str
    title: str
    description: str
    license: str
    license_url: str
    author: str
    source_url: str
    candidates: list[Candidate] = Field(default_factory=list)
    teacher: dict[str, dict[str, Any]] = Field(default_factory=dict)


class CandidateVerdict(BaseModel):
    cid: str
    problem: Literal[
        "none",
        "missing",
        "filename",
        "generic",
        "wrong_description",
        "decorative_needs_empty",
        "text_not_conveyed",
        "missing_data",
    ]
    suggested_alt: str = Field(default="", max_length=300)
    confidence: float = Field(ge=0.0, le=1.0)


class MultiVerdict(BaseModel):
    items: list[CandidateVerdict]


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html.unescape(text or ""))
    return re.sub(r"\s+", " ", text).strip()


def _manifest() -> list[Record]:
    path = DATA / "manifest.jsonl"
    if not path.exists():
        return []
    return [Record.model_validate_json(line) for line in path.read_text().splitlines() if line]


def _save(records: list[Record]) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "manifest.jsonl").write_text("".join(r.model_dump_json() + "\n" for r in records))


async def _get(client: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response | None:
    """GET with a few polite retries on network errors and 429/5xx; None if it keeps failing."""
    for attempt in range(4):
        try:
            response = await client.get(url, **kwargs)
        except httpx.TransportError as exc:
            print(f"  {type(exc).__name__} from {url[:60]}; retrying", flush=True)
            await asyncio.sleep(5 * 2**attempt)
            continue
        if response.status_code == 429 or response.status_code >= 500:
            print(f"  {response.status_code} from {url[:60]}; backing off", flush=True)
            await asyncio.sleep(float(response.headers.get("retry-after", 5 * 2**attempt)))
            continue
        return response
    return None


async def fetch(n: int) -> None:
    """Sample ``n`` licensed images with usable descriptions from Commons."""
    settings = get_settings()
    records = _manifest()
    seen = {r.title for r in records}
    limiter = RateLimiter(min_interval=1.0)
    headers = {"User-Agent": settings.user_agent}
    IMAGES.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(headers=headers, timeout=30, follow_redirects=True) as client:
        batch = 0
        while len(records) < n:
            await limiter.wait(API)
            params = {
                "action": "query",
                "format": "json",
                "generator": "random",
                "grnnamespace": "6",
                "grnlimit": "20",
                "prop": "imageinfo",
                "iiprop": "url|extmetadata|size|mime",
                "iiurlwidth": "512",
                "iiextmetadatafilter": "LicenseShortName|ImageDescription|Artist|LicenseUrl",
                # Identical URLs are served from Wikimedia's cache, so "random" would repeat the
                # same batch; requestid (echoed back by the API) makes every request distinct.
                "requestid": f"ramp-{len(records)}-{batch}",
            }
            batch += 1
            listing = await _get(client, API, params=params)
            if listing is None or listing.status_code != 200:
                continue
            pages = listing.json().get("query", {}).get("pages", {}).values()
            for page in pages:
                info = page.get("imageinfo", [{}])[0]
                meta = info.get("extmetadata", {})
                license_name = meta.get("LicenseShortName", {}).get("value", "")
                description = _clean(meta.get("ImageDescription", {}).get("value", ""))
                if (
                    page["title"] in seen
                    or info.get("mime") not in {"image/jpeg", "image/png"}
                    or not ALLOWED_LICENSES.match(license_name)
                    or not 20 <= len(description) <= 300
                    or "thumburl" not in info
                ):
                    continue
                await limiter.wait(info["thumburl"])
                image = await _get(client, info["thumburl"])
                if image is None or image.status_code != 200:
                    continue
                image_id = f"c{len(records):04d}"
                path = IMAGES / f"{image_id}.jpg"
                path.write_bytes(image.content)
                seen.add(page["title"])
                records.append(
                    Record(
                        image_id=image_id,
                        file=str(path.relative_to(DATA)),
                        title=page["title"],
                        description=description,
                        license=license_name,
                        license_url=meta.get("LicenseUrl", {}).get("value", ""),
                        author=_clean(meta.get("Artist", {}).get("value", ""))[:200],
                        source_url=info.get("descriptionurl", ""),
                    )
                )
                print(f"{len(records)}/{n} {page['title'][:70]} ({license_name})", flush=True)
                if len(records) >= n:
                    break
            _save(records)


def variants() -> None:
    """Attach the four constructed alt candidates to every image (deterministic)."""
    rng = random.Random(SEED)
    records = _manifest()
    for i, record in enumerate(records):
        other = records[(i + 1 + rng.randrange(len(records) - 1)) % len(records)]
        camera = rng.choice(["IMG", "DSC", "DSCF", "P", "PXL"])
        record.candidates = [
            Candidate(cid="a", alt=record.description[:150], intended="none"),
            Candidate(
                cid="b", alt=f"{camera}_{rng.randrange(1000, 9999)}.jpg", intended="filename"
            ),
            Candidate(cid="c", alt=rng.choice(GENERIC), intended="generic"),
            Candidate(cid="d", alt=other.description[:150], intended="wrong_description"),
        ]
        rng.shuffle(record.candidates)
    _save(records)


TEACHER_TASK = """Judge each candidate alt text for this one image, independently, as if each
were the image's only alt attribute on a web page with no other context. Return one item per
candidate id with problem (one of "none", "filename", "generic", "wrong_description",
"missing_data", "text_not_conveyed"), suggested_alt (the alt you would write), and confidence."""


async def teacher() -> None:
    settings = get_settings()
    transcript = Transcript()
    llm = StructuredLLM(settings.vision_model, transcript)
    system = f"{prompts.load('preamble')}\n\n{prompts.load('image_alt')}\n\n{TEACHER_TASK}"
    records = _manifest()
    for done, record in enumerate(records):
        if record.teacher:
            continue
        data = [{"cid": c.cid, "alt": c.alt} for c in record.candidates]
        user = [
            {"type": "text", "text": "Candidates:\n" + untrusted_block("page_data", data)},
            image_part((DATA / record.file).read_bytes(), max_side=384),
        ]
        try:
            verdict = await llm.complete(system=system, user=user, schema=MultiVerdict)
        except LLMError as exc:
            print(f"skip {record.image_id}: {exc}")
            continue
        record.teacher = {v.cid: v.model_dump() for v in verdict.items}
        if done % 10 == 0:
            _save(records)
            print(f"teacher {done + 1}/{len(records)} tokens={transcript.usage.prompt_tokens}")
    _save(records)
    print(transcript.usage)


def split_ids(records: list[Record]) -> dict[str, set[str]]:
    """Image-level 80/10/10 split, fixed by seed and independent of teacher output, so the test
    set never depends on which images the teacher happened to answer."""
    ids = sorted(r.image_id for r in records)
    random.Random(SEED).shuffle(ids)
    n = len(ids)
    return {
        "train": set(ids[: int(0.8 * n)]),
        "valid": set(ids[int(0.8 * n) : int(0.9 * n)]),
        "test": set(ids[int(0.9 * n) :]),
    }


def filter_and_split() -> None:
    """Agreement filter for train/valid, constructed labels for test, review queue.

    Train and valid keep a candidate only when the teacher agrees with its constructed label (the
    target uses the teacher's suggested alt). Test keeps every candidate with its constructed
    label, so student and teacher are both scored against labels neither of them produced.
    """
    records = _manifest()
    splits = split_ids(records)
    review: list[dict[str, Any]] = []
    stats: dict[str, Any] = {"kept": 0, "disagreed": 0, "no_teacher": 0}
    for name, ids in splits.items():
        lines = []
        for record in (r for r in records if r.image_id in ids):
            for cand in record.candidates:
                if name == "test":
                    lines.append(json.dumps(test_example(record, cand)))
                    continue
                verdict = record.teacher.get(cand.cid)
                if verdict is None:
                    stats["no_teacher"] += 1
                    continue
                if verdict["problem"] != cand.intended:
                    stats["disagreed"] += 1
                    review.append(
                        {
                            "image_id": record.image_id,
                            "file": record.file,
                            "alt": cand.alt,
                            "intended": cand.intended,
                            "teacher": verdict["problem"],
                        }
                    )
                    continue
                stats["kept"] += 1
                target = {
                    "problem": cand.intended,
                    "suggested_alt": verdict["suggested_alt"]
                    if cand.intended != "none"
                    else cand.alt,
                }
                lines.append(json.dumps(student_example(record.file, cand.alt, target)))
        stats[name] = len(lines)
        (DATA / f"{name}.jsonl").write_text("\n".join(lines) + "\n")
    (DATA / "review_queue.jsonl").write_text("".join(json.dumps(r) + "\n" for r in review))
    (DATA / "stats.json").write_text(json.dumps({**stats, "images": len(records)}, indent=2))
    print(stats)


def test_example(record: Record, cand: Candidate) -> dict[str, Any]:
    teacher = record.teacher.get(cand.cid, {})
    return {
        "image_id": record.image_id,
        "image": str(DATA / record.file),
        "alt": cand.alt,
        "label": cand.intended,
        "teacher": teacher.get("problem"),
    }


STUDENT_PROMPT = (
    "Judge this image's alt text for WCAG 1.1.1. Reply with JSON "
    '{"problem": one of none|filename|generic|wrong_description, "suggested_alt": string}. '
    "Alt text: "
)


def student_example(image: str, alt: str, target: dict[str, str]) -> dict[str, Any]:
    """One chat-format example (image + short instruction → compact JSON)."""
    return {
        "images": [str(DATA / image)],
        "messages": [
            {"role": "user", "content": STUDENT_PROMPT + json.dumps(alt)},
            {"role": "assistant", "content": json.dumps(target, ensure_ascii=False)},
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=["fetch", "variants", "teacher", "split", "all"])
    parser.add_argument("--images", type=int, default=250)
    args = parser.parse_args()
    if args.step in ("fetch", "all"):
        asyncio.run(fetch(args.images))
    if args.step in ("variants", "all"):
        variants()
    if args.step in ("teacher", "all"):
        asyncio.run(teacher())
    if args.step in ("split", "all"):
        filter_and_split()


if __name__ == "__main__":
    main()
