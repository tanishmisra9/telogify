"""Renders short bits of dynamic, per-weekend-colored text (driver name, event name, team-colored
labels) as PNG images instead of live HTML/CSS.

Why this exists: Gmail's automatic dark-mode color rewriting inverts live CSS `color`/`background`
declarations, which is fine for near-black ink (see email.py's module docstring) but crushes
bright/saturated brand colors -- Mercedes teal #27F4D2 measured collapsing to a near-invisible
#074231 on a real send. Pixels inside a hosted image are never touched by that rewriting (already
proven for the pace-spread swatches, the masthead logo, and the WINNER/section-title chips -- all
static PNGs). Driver names, event names, and team-colored labels can't be pre-baked as static
files because their text AND color change every weekend; this module generates them on demand
at send time (write side) and again on request (serve side, telogify.api.routes), both calling the
exact same function so the dimensions computed at send time always match what's actually served.

Font: Liberation Sans Bold (telogify/assets/fonts/, SIL Open Font License 1.1), a metrically
Arial-compatible open font -- chosen to match what Gmail's live text ALREADY falls back to (it
never fetches external stylesheets), the same lesson learned the hard way for the static chips
(see CLAUDE.md's Email digest section: baking chips in Archivo Black looked visibly wrong next to
Arial-fallback live text).
"""

from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_FONT_PATH = Path(__file__).parent / "assets" / "fonts" / "LiberationSans-Bold.ttf"

# ponytail: no letter-spacing support (PIL has no native kerning-gap API for it) -- only the
# insight-number badges used a subtle 0.04em in the live-CSS version. Add manual glyph-by-glyph
# advance if that specific gap turns out to matter once this renders on a real send.


@lru_cache(maxsize=8)
def _font(size_px: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_FONT_PATH), size_px)


def measure_text_chip(
    text: str, *, font_size: int, padding: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> tuple[int, int]:
    """Logical (CSS px, not retina-scaled) width/height the chip will render at. Callable from
    email.py at send time without touching the network, so the <img width/height> attributes
    always match what the /chip/text.png route later serves for the identical parameters."""
    top, right, bottom, left = padding
    font = _font(font_size)
    left_bear, top_bear, text_right, text_bottom = font.getbbox(text)
    width = (text_right - left_bear) + left + right
    height = (text_bottom - top_bear) + top + bottom
    return width, height


def render_text_chip_png(
    text: str,
    *,
    font_size: int,
    text_color: str,
    bg_color: str | None = None,
    padding: tuple[int, int, int, int] = (0, 0, 0, 0),
    border_radius: int = 0,
    scale: int = 3,
) -> bytes:
    """PNG bytes at `scale`x resolution (retina-sharp when displayed at the logical size from
    measure_text_chip -- same reasoning as the static chips' deviceScaleFactor:3 renders)."""
    top, right, bottom, left = padding
    width, height = measure_text_chip(text, font_size=font_size, padding=padding)
    font = _font(font_size * scale)
    left_bear, top_bear, *_ = font.getbbox(text)

    img = Image.new("RGBA", (width * scale, height * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if bg_color is not None:
        draw.rounded_rectangle(
            [0, 0, width * scale - 1, height * scale - 1],
            radius=border_radius * scale, fill=bg_color,
        )
    draw.text(
        (left * scale - left_bear, top * scale - top_bear), text, font=font, fill=text_color,
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
