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
Arial-fallback live text). Font SIZES for each call site match the already-approved, already-
bumped sizes baked into the static WINNER/section-title chips (see email.py call sites), not the
smaller original live-CSS values -- using the smaller ones here once made every dynamic chip look
noticeably thinner/smaller than its static neighbors in the same email.
"""

from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_FONT_PATH = Path(__file__).parent / "assets" / "fonts" / "LiberationSans-Bold.ttf"


@lru_cache(maxsize=8)
def _font(size_px: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_FONT_PATH), size_px)


def _char_advances(text: str, font: ImageFont.FreeTypeFont, spacing_px: float) -> list[float]:
    """Per-character advance widths (PIL getlength already includes the glyph's own right-side
    bearing, matching browser layout metrics), each with the letter-spacing gap added after it
    except the last -- CSS letter-spacing adds the gap between characters, not a trailing gap."""
    advances = [font.getlength(c) for c in text]
    return [a + spacing_px for a in advances[:-1]] + advances[-1:] if advances else []


def text_baseline_offset(font_size: int) -> int:
    """CSS `vertical-align` (in px, negative) that puts an inline text chip's own baseline on the
    baseline of the live text beside it.

    A chip's height is ascent+descent (see measure_text_chip), so its baseline sits `descent` up
    from its bottom edge -- which is exactly where a text run's baseline sits relative to its
    descender. Hence -descent. Derived rather than hardcoded on purpose: the driver-name chip
    carried a hand-tuned -7px from an earlier build whose chips were cropped tight to the ink,
    and changing the height metric silently invalidated it, dropping the name off the headline's
    baseline. Anything derived from the font cannot go stale that way."""
    _, descent = _font(font_size).getmetrics()
    return -descent


def measure_text_chip(
    text: str,
    *,
    font_size: int,
    padding: tuple[int, int, int, int] = (0, 0, 0, 0),
    letter_spacing_em: float = 0.0,
) -> tuple[int, int]:
    """Logical (CSS px, not retina-scaled) width/height the chip will render at. Callable from
    email.py at send time without touching the network, so the <img width/height> attributes
    always match what the /chip/text.png route later serves for the identical parameters.

    Height uses the font's typographic ascent+descent (getmetrics), not the tight ink bounding
    box (getbbox) -- ink height for all-caps text like "SECTOR 1" is ~10px at 15px font-size,
    while ascent+descent is ~18px. Using the tight box rendered every chip noticeably more
    cramped/squished than the equivalent live CSS text, which gets the font's natural line-height
    leading above and below the glyphs for free; ascent+descent reproduces that leading."""
    top, right, bottom, left = padding
    font = _font(font_size)
    spacing_px = letter_spacing_em * font_size
    text_width = sum(_char_advances(text, font, spacing_px))
    ascent, descent = font.getmetrics()
    width = round(text_width) + left + right
    height = ascent + descent + top + bottom
    return width, height


def render_text_chip_png(
    text: str,
    *,
    font_size: int,
    text_color: str,
    bg_color: str | None = None,
    padding: tuple[int, int, int, int] = (0, 0, 0, 0),
    border_radius: int = 0,
    letter_spacing_em: float = 0.0,
    scale: int = 3,
) -> bytes:
    """PNG bytes at `scale`x resolution (retina-sharp when displayed at the logical size from
    measure_text_chip -- same reasoning as the static chips' deviceScaleFactor:3 renders)."""
    top, right, bottom, left = padding
    width, height = measure_text_chip(
        text, font_size=font_size, padding=padding, letter_spacing_em=letter_spacing_em,
    )
    font = _font(font_size * scale)
    spacing_px = letter_spacing_em * font_size * scale

    img = Image.new("RGBA", (width * scale, height * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if bg_color is not None:
        draw.rounded_rectangle(
            [0, 0, width * scale - 1, height * scale - 1],
            radius=border_radius * scale, fill=bg_color,
        )
    # No top_bear subtraction: PIL's default text anchor ("la") places (x, y) at the font's own
    # ascender line, which is exactly the reference point measure_text_chip's height is built
    # from -- drawing here (rather than nudging up to the tight ink top) is what gives the
    # natural leading above the glyphs.
    x = left * scale
    y = top * scale
    for char, advance in zip(text, _char_advances(text, font, spacing_px)):
        draw.text((x, y), char, font=font, fill=text_color)
        x += advance

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
