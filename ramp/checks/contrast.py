"""WCAG contrast math (SC 1.4.3 / 1.4.11), kept pure so it is easy to test and explain.

Definitions follow WCAG 2.x: relative luminance from sRGB, ratio = (L1 + 0.05) / (L2 + 0.05).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_RGB = re.compile(r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)")

LARGE_TEXT_PX = 24.0  # 18pt
LARGE_BOLD_TEXT_PX = 18.66  # 14pt bold


@dataclass(frozen=True)
class RGBA:
    r: float
    g: float
    b: float
    a: float = 1.0

    def over(self, background: RGBA) -> RGBA:
        """Alpha-composite this colour over an opaque background ("source over")."""
        a = self.a
        return RGBA(
            r=self.r * a + background.r * (1 - a),
            g=self.g * a + background.g * (1 - a),
            b=self.b * a + background.b * (1 - a),
            a=1.0,
        )


WHITE = RGBA(255, 255, 255)


def parse_css_color(value: str) -> RGBA:
    """Parse a computed CSS colour (``rgb(...)``/``rgba(...)``, as browsers report them)."""
    text = value.strip().lower()
    if text == "transparent":
        return RGBA(0, 0, 0, 0.0)
    match = _RGB.fullmatch(text)
    if match is None:
        raise ValueError(f"unsupported colour: {value!r}")
    r, g, b, a = match.groups()
    alpha = 1.0
    if a is not None:
        alpha = float(a[:-1]) / 100 if a.endswith("%") else float(a)
    return RGBA(float(r), float(g), float(b), alpha)


def _channel(c: float) -> float:
    s = c / 255.0
    return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4


def relative_luminance(color: RGBA) -> float:
    return 0.2126 * _channel(color.r) + 0.7152 * _channel(color.g) + 0.0722 * _channel(color.b)


def contrast_ratio(foreground: RGBA, background: RGBA) -> float:
    """Contrast ratio between two colours; a translucent foreground is composited first."""
    bg = background if background.a >= 1.0 else background.over(WHITE)
    fg = foreground if foreground.a >= 1.0 else foreground.over(bg)
    lighter, darker = sorted((relative_luminance(fg), relative_luminance(bg)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def is_large_text(font_size_px: float, font_weight: int) -> bool:
    return font_size_px >= LARGE_TEXT_PX or (
        font_weight >= 700 and font_size_px >= LARGE_BOLD_TEXT_PX
    )


def required_ratio(font_size_px: float, font_weight: int) -> float:
    """Minimum ratio for SC 1.4.3 (AA): 3:1 for large text, 4.5:1 otherwise."""
    return 3.0 if is_large_text(font_size_px, font_weight) else 4.5
