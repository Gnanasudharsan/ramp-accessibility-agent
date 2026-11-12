"""In-page probes used by the MCP server and the audit pipeline: contrast, focus order, boxes.

Each probe returns plain data. Page-derived strings (names, text) are untrusted and are always
returned in data fields, never interpolated into instructions.
"""

from __future__ import annotations

from typing import Any

from playwright.async_api import Page
from pydantic import BaseModel

from ramp.checks.contrast import contrast_ratio, is_large_text, parse_css_color, required_ratio
from ramp.report.schema import BoundingBox

# Shared JS helper: a short, unique CSS path for an element.
CSS_PATH_JS = """
function cssPath(el) {
  if (!(el instanceof Element)) return '';
  if (el.id && document.querySelectorAll('#' + CSS.escape(el.id)).length === 1)
    return '#' + CSS.escape(el.id);
  const parts = [];
  while (el && el.nodeType === 1 && el !== document.documentElement) {
    let part = el.localName;
    const parent = el.parentElement;
    if (parent) {
      const same = Array.from(parent.children).filter(c => c.localName === el.localName);
      if (same.length > 1) part += ':nth-of-type(' + (same.indexOf(el) + 1) + ')';
    }
    parts.unshift(part);
    if (el.id && document.querySelectorAll('#' + CSS.escape(el.id)).length === 1) {
      parts[0] = '#' + CSS.escape(el.id);
      break;
    }
    el = parent;
  }
  return parts.join(' > ');
}
"""


class ContrastResult(BaseModel):
    selector: str
    found: bool
    text_sample: str = ""
    foreground: str = ""
    background: str = ""
    font_size_px: float = 0.0
    font_weight: int = 400
    large_text: bool = False
    ratio: float | None = None
    required: float | None = None
    passes: bool | None = None
    indeterminate_reason: str | None = None


async def contrast_check(page: Page, selector: str) -> ContrastResult:
    """Text contrast for the first element matching ``selector`` (SC 1.4.3).

    The background is found by walking ancestors and compositing translucent layers over white.
    A background image or gradient makes the result indeterminate rather than guessed.
    """
    data: dict[str, Any] | None = await page.evaluate(
        r"""(selector) => {
          const el = document.querySelector(selector);
          if (!el) return null;
          const cs = getComputedStyle(el);
          const layers = [];
          let image = null;
          const alpha = (c) => {
            const m = c.match(/rgba?\(([^)]+)\)/);
            if (!m) return 1;
            const parts = m[1].split(/[\s,\/]+/).filter(Boolean);
            return parts.length > 3 ? parseFloat(parts[3]) : 1;
          };
          for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
            const s = getComputedStyle(n);
            if (s.backgroundImage && s.backgroundImage !== 'none') {
              image = s.backgroundImage;
              break;
            }
            layers.push(s.backgroundColor);
            if (alpha(s.backgroundColor) >= 1) break;  // opaque layer: nothing behind matters
          }
          return {
            text: (el.innerText || el.value || '').trim().slice(0, 120),
            color: cs.color, layers, image,
            fontSize: parseFloat(cs.fontSize), fontWeight: parseInt(cs.fontWeight, 10) || 400,
          };
        }""",
        selector,
    )
    if data is None:
        return ContrastResult(selector=selector, found=False)

    size, weight = float(data["fontSize"]), int(data["fontWeight"])
    result = ContrastResult(
        selector=selector,
        found=True,
        text_sample=data["text"],
        foreground=data["color"],
        font_size_px=size,
        font_weight=weight,
        large_text=is_large_text(size, weight),
        required=required_ratio(size, weight),
    )
    if data["image"]:
        result.indeterminate_reason = "background image or gradient behind text"
        return result

    # Composite from the outermost collected layer inwards, starting on white.
    background = parse_css_color("rgb(255, 255, 255)")
    for layer in reversed(data["layers"]):
        background = parse_css_color(layer).over(background)
    result.background = f"rgb({background.r:.0f}, {background.g:.0f}, {background.b:.0f})"
    ratio = contrast_ratio(parse_css_color(data["color"]), background)
    result.ratio = round(ratio, 2)
    result.passes = ratio >= (result.required or 4.5)
    return result


class FocusStop(BaseModel):
    index: int
    selector: str
    tag: str
    role: str | None
    name: str  # untrusted page text
    box: BoundingBox | None
    indicator_visible: bool  # focused style differs from unfocused style (SC 2.4.7 heuristic)
    in_viewport: bool


class FocusOrderResult(BaseModel):
    stops: list[FocusStop]
    possible_trap: str | None = None  # selector where focus stopped moving (SC 2.1.2)
    cycled: bool = False  # focus returned to the first stop or left the document


async def focus_order(page: Page, max_steps: int = 60) -> FocusOrderResult:
    """Press Tab repeatedly and record each focused element (SC 2.4.3, 2.4.7, 2.1.2)."""
    probe = (
        "() => {"
        + CSS_PATH_JS
        + """
        {
          const el = document.activeElement;
          if (!el || el === document.body || el === document.documentElement) return null;
          const keys = ['outlineStyle','outlineWidth','outlineColor','boxShadow','borderColor',
                        'backgroundColor','color','textDecorationLine'];
          const snap = () => {
            const s = getComputedStyle(el);
            return keys.map(k => s[k]).join('|');
          };
          const focused = snap();
          el.blur();
          const unfocused = snap();
          el.focus({preventScroll: true});
          const r = el.getBoundingClientRect();
          const name = (el.getAttribute('aria-label') || el.innerText || el.getAttribute('alt')
                        || el.getAttribute('title') || el.value || '').trim().slice(0, 120);
          return {
            selector: cssPath(el), tag: el.localName, role: el.getAttribute('role'), name,
            box: {x: r.x + scrollX, y: r.y + scrollY, width: r.width, height: r.height},
            indicator: focused !== unfocused,
            inViewport: r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth,
          };
        }
        }"""
    )
    stops: list[FocusStop] = []
    trap: str | None = None
    cycled = False
    repeats = 0
    await page.evaluate("document.activeElement && document.activeElement.blur()")
    for i in range(max_steps):
        await page.keyboard.press("Tab")
        info: dict[str, Any] | None = await page.evaluate(probe)
        if info is None:
            if stops:
                cycled = True
                break
            continue
        if stops and info["selector"] == stops[0].selector:
            cycled = True
            break
        if stops and info["selector"] == stops[-1].selector:
            repeats += 1
            if repeats >= 3:
                trap = info["selector"]
                break
            continue
        repeats = 0
        stops.append(
            FocusStop(
                index=i,
                selector=info["selector"],
                tag=info["tag"],
                role=info["role"],
                name=info["name"],
                box=BoundingBox(**info["box"]),
                indicator_visible=bool(info["indicator"]),
                in_viewport=bool(info["inViewport"]),
            )
        )
    return FocusOrderResult(stops=stops, possible_trap=trap, cycled=cycled)


async def element_boxes(page: Page, selectors: list[str]) -> dict[str, BoundingBox]:
    """Page-coordinate boxes for plain CSS selectors (iframe/shadow targets are skipped)."""
    plain = [s for s in selectors if ">>>" not in s]
    raw: dict[str, dict[str, float]] = await page.evaluate(
        """(selectors) => {
          const out = {};
          for (const s of selectors) {
            let el = null;
            try { el = document.querySelector(s); } catch (e) { continue; }
            if (!el) continue;
            const r = el.getBoundingClientRect();
            if (r.width === 0 && r.height === 0) continue;
            out[s] = {x: r.x + scrollX, y: r.y + scrollY, width: r.width, height: r.height};
          }
          return out;
        }""",
        plain,
    )
    return {sel: BoundingBox(**box) for sel, box in raw.items()}


async def outer_html(page: Page, selector: str, limit: int = 4000) -> str | None:
    html: str | None = await page.evaluate(
        "(s) => { const el = document.querySelector(s); return el ? el.outerHTML : null; }",
        selector,
    )
    return html[:limit] if html is not None else None
