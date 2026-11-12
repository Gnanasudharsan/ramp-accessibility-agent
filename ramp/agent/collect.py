"""Collect evidence for judgment-based checks while a page is open.

Nothing here decides whether something is a barrier. It gathers *candidates* (images, links,
heading-like text, tables, media, instructions) with the DOM context a reviewer would need, plus
screenshot crops. Judgment happens in ``vision.py``. All strings are untrusted page content.

One check here is decided deterministically: focus visibility (SC 2.4.7). Each focus stop is
screenshotted focused and unfocused; identical pixels mean no visible indicator. A pixel diff is
more reliable than asking a model whether two crops differ.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops
from playwright.async_api import FloatRect, Page
from pydantic import BaseModel, Field

from ramp.checks.probes import CSS_PATH_JS
from ramp.report.schema import BoundingBox


class ImageCandidate(BaseModel):
    cid: str
    selector: str
    html: str
    alt: str | None  # None = attribute missing
    src_file: str
    in_link: bool
    link_href: str | None = None
    link_text: str = ""  # other text inside the same link
    nearby_text: str = ""
    box: BoundingBox | None = None
    crop_path: str | None = None  # written by the agent, relative to the audit output dir
    crop_png: bytes | None = Field(default=None, exclude=True)


class LinkCandidate(BaseModel):
    cid: str
    selector: str
    html: str
    name: str  # accessible name, approximated
    href: str
    context: str  # enclosing p / li / td / th / dd text, the programmatic link context
    heading: str  # nearest preceding heading text
    same_name_other_targets: int = 0


class StructureCandidate(BaseModel):
    cid: str
    selector: str
    kind: str  # heading_like | table | media | instructions | form
    html: str
    text: str
    details: dict[str, Any] = Field(default_factory=dict)


class FocusFinding(BaseModel):
    selector: str
    html: str
    name: str
    changed_pixels: int
    box: BoundingBox


class PageEvidence(BaseModel):
    url: str
    title: str
    images: list[ImageCandidate] = Field(default_factory=list)
    links: list[LinkCandidate] = Field(default_factory=list)
    structure: list[StructureCandidate] = Field(default_factory=list)
    focus_without_indicator: list[FocusFinding] = Field(default_factory=list)
    focus_stops_checked: int = 0
    screenshot_path: str | None = None
    screenshot_png: bytes | None = Field(default=None, exclude=True)

    def save_images(self, out_dir: Path, slug: str) -> None:
        """Persist screenshot and crops so the evidence survives checkpointing."""
        folder = out_dir / "candidates" / slug
        folder.mkdir(parents=True, exist_ok=True)
        if self.screenshot_png is not None:
            (folder / "page.png").write_bytes(self.screenshot_png)
            self.screenshot_path = str((folder / "page.png").relative_to(out_dir))
        for image in self.images:
            if image.crop_png is not None:
                path = folder / f"{image.cid}.png"
                path.write_bytes(image.crop_png)
                image.crop_path = str(path.relative_to(out_dir))


_COLLECT_JS = (
    "(maxImages) => {"
    + CSS_PATH_JS
    + (Path(__file__).parent / "js" / "collect.js").read_text(encoding="utf-8")
    + "}"
)


def _crop(screenshot: bytes, box: BoundingBox, pad: int = 6) -> bytes | None:
    with Image.open(io.BytesIO(screenshot)) as img:
        left, top = max(0, int(box.x) - pad), max(0, int(box.y) - pad)
        right = min(img.width, int(box.x + box.width) + pad)
        bottom = min(img.height, int(box.y + box.height) + pad)
        if right - left < 4 or bottom - top < 4:
            return None
        buf = io.BytesIO()
        img.crop((left, top, right, bottom)).save(buf, format="PNG")
        return buf.getvalue()


async def collect_evidence(page: Page, max_images: int = 15) -> PageEvidence:
    """Gather candidates and crops from the open page. Read-only: no clicks, no input."""
    screenshot = await page.screenshot(full_page=True)
    raw: dict[str, Any] = await page.evaluate(_COLLECT_JS, max_images)
    evidence = PageEvidence(url=page.url, title=await page.title(), screenshot_png=screenshot)
    for i, item in enumerate(raw["images"]):
        image = ImageCandidate(cid=f"img{i + 1}", **item)
        if image.box is not None:
            image.crop_png = _crop(screenshot, image.box)
        evidence.images.append(image)
    evidence.links = [LinkCandidate(cid=f"link{i + 1}", **x) for i, x in enumerate(raw["links"])]
    evidence.structure = [
        StructureCandidate(cid=f"s{i + 1}", **x) for i, x in enumerate(raw["structure"])
    ]
    found, checked = await focus_visibility(page)
    evidence.focus_without_indicator, evidence.focus_stops_checked = found, checked
    return evidence


_FOCUS_INFO_JS = (
    "() => {"
    + CSS_PATH_JS
    + """
  const el = document.activeElement;
  if (!el || el === document.body || el === document.documentElement) return null;
  el.scrollIntoView({block: 'center'});
  const r = el.getBoundingClientRect();
  return {selector: cssPath(el), html: el.outerHTML.slice(0, 400),
          name: (el.getAttribute('aria-label') || el.innerText || '').trim().slice(0, 80),
          box: {x: r.x + scrollX, y: r.y + scrollY, width: r.width, height: r.height}};
}"""
)


async def focus_visibility(page: Page, max_stops: int = 25) -> tuple[list[FocusFinding], int]:
    """Tab through the page; compare each stop's pixels focused vs unfocused (SC 2.4.7)."""
    findings: list[FocusFinding] = []
    seen: set[str] = set()
    await page.evaluate("document.activeElement && document.activeElement.blur()")
    checked = 0
    for _ in range(max_stops):
        await page.keyboard.press("Tab")
        info: dict[str, Any] | None = await page.evaluate(_FOCUS_INFO_JS)
        if info is None or info["selector"] in seen:
            break
        seen.add(info["selector"])
        b = info["box"]
        if b["width"] < 1 or b["height"] < 1:
            continue
        pad = 8  # indicators usually sit just outside the element (outline-offset)
        clip = FloatRect(
            x=max(0, b["x"] - pad),
            y=max(0, b["y"] - pad),
            width=b["width"] + 2 * pad,
            height=b["height"] + 2 * pad,
        )
        focused = await page.screenshot(clip=clip, full_page=True)
        await page.evaluate(
            "(s) => { const el = document.querySelector(s); el && el.blur(); }", info["selector"]
        )
        unfocused = await page.screenshot(clip=clip, full_page=True)
        await page.evaluate(
            "(s) => { const el = document.querySelector(s); el && el.focus(); }", info["selector"]
        )
        checked += 1
        changed = _changed_pixels(focused, unfocused)
        if changed == 0:
            findings.append(
                FocusFinding(
                    selector=info["selector"],
                    html=info["html"],
                    name=info["name"],
                    changed_pixels=0,
                    box=BoundingBox(**b),
                )
            )
    await page.evaluate("window.scrollTo(0, 0)")
    return findings, checked


def _changed_pixels(a: bytes, b: bytes) -> int:
    with Image.open(io.BytesIO(a)) as ia, Image.open(io.BytesIO(b)) as ib:
        if ia.size != ib.size:
            return ia.size[0] * ia.size[1]
        diff = ImageChops.difference(ia.convert("RGB"), ib.convert("RGB")).convert("L")
        # Count pixels that changed by more than a small anti-aliasing tolerance.
        return int(diff.point(lambda v: 255 if v > 8 else 0).histogram()[255])
