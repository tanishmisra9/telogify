"""Probe A (color calibration) and Probe B (CSS support matrix). Pure HTML generation, no I/O.

This module is the single source of geometry truth for both probes. `extract.py` imports
`CELL_PX` and `FRAME_COLOR` from here and computes every sample coordinate from a located grid's
own measured pixel size -- never a hardcoded coordinate -- so the HTML generator and the pixel
extractor can never silently drift out of sync with each other.

Layout: each `GridSpec`'s swatches are wrapped in a one-cell-wide magenta frame (a color no real
swatch uses), rendered as a plain Gmail-safe `<table>` (role=presentation, cellpadding/cellspacing
0, no CSS layout properties -- exactly the idiom already used throughout email.py). The frame
lets extract.py locate the grid in an arbitrary screenshot (which also contains Gmail's own UI
chrome around the message) by finding a connected blob of magenta-ish pixels; dividing that
blob's own measured size by (cols+2)/(rows+2) cells gives the true CSS-px-to-screenshot-px scale
without needing to assume anything about zoom level or device pixel ratio.
"""

from __future__ import annotations

import base64
import colorsys
import struct
import zlib
from dataclasses import dataclass
from typing import Callable

FRAME_COLOR = "#FF00FF"
CELL_PX = 40


@dataclass(frozen=True)
class GridSpec:
    name: str
    rows: int
    cols: int
    swatches: list[str]  # hex values, row-major order, must have exactly rows*cols entries

    def __post_init__(self) -> None:
        if len(self.swatches) != self.rows * self.cols:
            raise ValueError(
                f"grid {self.name!r}: {len(self.swatches)} swatches for a "
                f"{self.rows}x{self.cols} grid (need {self.rows * self.cols})"
            )

    def swatch_at(self, row: int, col: int) -> str:
        return self.swatches[row * self.cols + col]


def _grayscale_ramp(steps: int = 24) -> list[str]:
    return [
        f"#{v:02x}{v:02x}{v:02x}"
        for v in (round(i * 255 / (steps - 1)) for i in range(steps))
    ]


def _chromatic_grid(hues: tuple[int, ...] = (0, 60, 120, 180, 240, 300)) -> list[str]:
    """6 hues x 5 lightness steps at a fixed, fairly saturated chroma -- enough to tell whether
    Gmail's inversion treats chromatic and achromatic colors differently, and whether hue
    survives at all lightness levels."""
    lightnesses = (0.20, 0.35, 0.50, 0.65, 0.80)
    swatches = []
    for lightness in lightnesses:
        for hue in hues:
            r, g, b = colorsys.hls_to_rgb(hue / 360, lightness, 0.70)
            swatches.append(f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}")
    return swatches


# The digest's own shipped colors (telogify/email.py) -- the ones the actual dark-mode question
# is about. Kept in sync by hand since email.py's constants aren't structured for reuse here;
# see test_emailsim.py for a pin against email.py's literal hex values.
BRAND_SWATCHES: list[str] = [
    "#0a0a0a",  # ink (_NB_INK)
    "#E10600",  # brand red
    "#FEFEFE",  # off-white panel default
    "#f2f2ea",  # .page background
    "#fdfdfb",  # .sheet background
    "#FFE500",  # highlight yellow
    "#16160f",  # dark-mode .page background
    "#29291f",  # dark-mode panel background
    "#3671C6",  # Red Bull Racing
    "#E8002D",  # Ferrari
    "#27F4D2",  # Mercedes
    "#FF8000",  # McLaren
    "#229971",  # Aston Martin
    "#64C4FF",  # Williams
]


def probe_a_grids() -> list[GridSpec]:
    return [
        GridSpec("grayscale", rows=4, cols=6, swatches=_grayscale_ramp(24)),
        GridSpec("chromatic", rows=5, cols=6, swatches=_chromatic_grid()),
        GridSpec("brand", rows=2, cols=7, swatches=BRAND_SWATCHES),
    ]


def _swatch_td(hexval: str, cell_px: int = CELL_PX) -> str:
    # font-size:0/line-height:0 collapses the cell to exactly cell_px with no text-baseline
    # padding; &nbsp; keeps some mail clients from collapsing an empty <td> to zero height.
    return (
        f'<td width="{cell_px}" height="{cell_px}" '
        f'style="width:{cell_px}px;height:{cell_px}px;background:{hexval};padding:0;'
        f'margin:0;border:0;font-size:0;line-height:0;">&nbsp;</td>'
    )


def _frame_td(cell_px: int = CELL_PX) -> str:
    return (
        f'<td width="{cell_px}" height="{cell_px}" '
        f'style="width:{cell_px}px;height:{cell_px}px;background:{FRAME_COLOR};padding:0;'
        f'margin:0;border:0;font-size:0;line-height:0;">&nbsp;</td>'
    )


def _readout_td(inner_html: str, cell_px: int = CELL_PX) -> str:
    """A cell_px-square cell for Probe B: instead of a flat color, its background is whatever
    the tested CSS actually resolves to at the cell's own center -- `overflow:hidden` clips any
    test construction (rotated shapes, box-shadow offsets) exactly to the frame grid's own
    geometry, so extract.py's existing `_cell_center`/`sample_patch` need no changes at all to
    read a Probe B cell the same way they read a Probe A swatch. Deliberately does NOT set
    `position` on the wrapper itself -- individual test snippets that need a positioning context
    establish it themselves, since `position` support is one of the things being tested and
    shouldn't be silently assumed by the scaffold."""
    return (
        f'<td width="{cell_px}" height="{cell_px}" style="width:{cell_px}px;height:{cell_px}px;'
        f'padding:0;margin:0;border:0;font-size:0;line-height:0;overflow:hidden;">'
        f'<div style="width:{cell_px}px;height:{cell_px}px;overflow:hidden;">{inner_html}</div></td>'
    )


def _frame_table_html(rows: int, cols: int, cell_htmls: list[str], cell_px: int = CELL_PX) -> str:
    """Generic magenta-framed table shared by Probe A (flat-color cells) and Probe B (readout
    cells): a one-cell-wide magenta border around a rows x cols grid of arbitrary pre-rendered
    `<td>` HTML, row-major. Both `_swatch_td` and `_readout_td` produce cells this can wrap."""
    if len(cell_htmls) != rows * cols:
        raise ValueError(f"{len(cell_htmls)} cells for a {rows}x{cols} grid (need {rows * cols})")
    frame_row = f"<tr>{_frame_td(cell_px) * (cols + 2)}</tr>"
    out_rows = [frame_row]
    idx = 0
    for _ in range(rows):
        cells = [_frame_td(cell_px)]
        cells.extend(cell_htmls[idx + c] for c in range(cols))
        idx += cols
        cells.append(_frame_td(cell_px))
        out_rows.append(f"<tr>{''.join(cells)}</tr>")
    out_rows.append(frame_row)
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        f'style="border-collapse:collapse;">{"".join(out_rows)}</table>'
    )


def _grid_table_html(grid: GridSpec) -> str:
    cells = [_swatch_td(grid.swatch_at(r, c)) for r in range(grid.rows) for c in range(grid.cols)]
    return _frame_table_html(grid.rows, grid.cols, cells)


def render_probe_a() -> str:
    """Full standalone HTML document for the color-calibration probe. Grids stack vertically
    with generous margin between them so their magenta frames never touch -- extract.py finds
    each one as a separate connected component and orders them top-to-bottom, which must match
    the order `probe_a_grids()` returns."""
    sections = []
    for grid in probe_a_grids():
        caption = f"{grid.name} &middot; {grid.rows * grid.cols} swatches &middot; row-major"
        sections.append(
            '<div style="margin-bottom:40px;">'
            f'<p style="font-family:monospace;font-size:11px;color:#333;margin:0 0 8px;">{caption}</p>'
            f"{_grid_table_html(grid)}"
            "</div>"
        )
    body = "".join(sections)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Telogify emailsim -- Probe A (color)</title>
</head>
<body style="margin:0;padding:20px;background:#ffffff;">
{body}
</body>
</html>"""


# ---------------------------------------------------------------------------------------------
# Probe B: the CSS support matrix.
#
# Each CssTest constructs a small self-contained readout that renders one reference color if the
# tested CSS actually applies and a different reference color if it doesn't -- e.g. two block
# children that sit side by side (covering the cell's center) if `display:flex` works, or stack
# vertically (leaving the center showing the container's own background) if it falls back to
# plain block flow. This turns "does property X work" into the same color-classification problem
# extract.py already solves for Probe A, just checked against per-test reference colors instead
# of a single expected value -- see extract.py's classify_css_tests.
#
# Every test's geometry is designed so the cell's CENTER point (the only point extract.py
# samples, via `_cell_center`) lands unambiguously on one reference color or the other with a
# real pixel margin -- never on a shared edge -- and every test's "supported" branch is verified
# against a full-CSS-support renderer (Chromium via playwright-cli) before this probe is ever
# sent anywhere real. See the emailsim plan for that verification step.
# ---------------------------------------------------------------------------------------------

CELL_PX_B = 60
_GREEN = "#00FF00"
_RED = "#FF0000"


@dataclass(frozen=True)
class CssTest:
    id: str
    label: str
    html: str
    references: list[tuple[str, str]]  # (verdict, hex) pairs; classified by nearest color

    def hex_for(self, verdict: str) -> str:
        for v, hexval in self.references:
            if v == verdict:
                return hexval
        raise KeyError(verdict)


def _binary_test(id_: str, label: str, html: str, *, supported_hex: str = _GREEN, fallback_hex: str = _RED) -> CssTest:
    return CssTest(id_, label, html, [("supported", supported_hex), ("fallback", fallback_hex)])


def _side_by_side_reveal(id_: str, label: str, *, container_style: str, child1_style: str = "", child2_style: str = "") -> CssTest:
    """Shared construction for 'does this property make two block children sit side by side
    instead of stacking' (flex, grid, float). child2 (green) is sized to cover the cell's
    horizontal center once side by side; in the block-flow fallback it stacks below child1 and
    is clipped away by the wrapper's overflow:hidden, leaving the container's own red background
    at the sample point."""
    c1w = CELL_PX_B // 4
    c2w = CELL_PX_B - c1w
    html = (
        f'<div style="width:{CELL_PX_B}px;height:{CELL_PX_B}px;background:{_RED};{container_style}">'
        f'<div style="width:{c1w}px;height:{CELL_PX_B}px;{child1_style}"></div>'
        f'<div style="width:{c2w}px;height:{CELL_PX_B}px;background:{_GREEN};{child2_style}"></div>'
        "</div>"
    )
    return _binary_test(id_, label, html)


def _display_flex_test() -> CssTest:
    return _side_by_side_reveal("display_flex", "display:flex", container_style="display:flex;")


def _display_grid_test() -> CssTest:
    return _side_by_side_reveal(
        "display_grid", "display:grid",
        container_style="display:grid;grid-template-columns:auto 1fr;",
    )


def _float_test() -> CssTest:
    return _side_by_side_reveal(
        "float", "float:left (children)", container_style="",
        child1_style="float:left;", child2_style="float:left;",
    )


def _position_absolute_test() -> CssTest:
    """A spacer div pushes normal-flow content below the visible cell; only `position:absolute`
    (removing the green child from flow, placing it at top:0/left:0 relative to the container)
    brings it back to cover the center. Isolated from the negative_margin/transform tests below,
    which use a different mechanism entirely."""
    html = (
        f'<div style="width:{CELL_PX_B}px;height:{CELL_PX_B}px;background:{_RED};position:relative;overflow:hidden;">'
        f'<div style="height:{CELL_PX_B}px;"></div>'
        f'<div style="position:absolute;top:0;left:0;width:{CELL_PX_B}px;height:{CELL_PX_B}px;background:{_GREEN};"></div>'
        "</div>"
    )
    return _binary_test("position_absolute", "position:absolute + offsets", html)


def _negative_margin_test() -> CssTest:
    """Defect candidate: `_tile_rotations` (email.py) still ships `margin-top:-4px`/`-6px` on
    the same wrappers as `transform:rotate`. If Gmail drops the transform but honors the
    negative margin (or vice versa -- see _transform_rotate_test), a practice tile silently sits
    a few px out of place. Tested independently of transform here: the green child starts in
    normal flow filling the container exactly (margin-top:0 behavior). A negative top margin
    shifts a block's own top edge UPWARD relative to its normal position -- NOT toward/over
    later content -- so if honored, the full-height green child moves entirely above the
    container's visible bounds (page y:[-60,0] against the container's [0,60]) and is clipped
    away by overflow:hidden, revealing the container's own red. If the negative value is instead
    dropped (treated as 0, i.e. NOT honored), the child stays in its normal position, fully
    covering the container -- green. Verdicts are therefore inverted from the naive "green means
    it moved into place" assumption: supported (honored) -> red, fallback (ignored) -> green."""
    html = (
        f'<div style="width:{CELL_PX_B}px;height:{CELL_PX_B}px;background:{_RED};overflow:hidden;">'
        f'<div style="width:{CELL_PX_B}px;height:{CELL_PX_B}px;background:{_GREEN};margin-top:-{CELL_PX_B}px;"></div>'
        "</div>"
    )
    return _binary_test("negative_margin", "margin-top: negative (defect candidate)", html, supported_hex=_RED, fallback_hex=_GREEN)


def _transform_rotate_test() -> CssTest:
    """CORRECTED 2026-08-02. The original version of this test used `rotate(180deg)` around an
    off-center transform-origin -- which, for an axis-aligned rectangle, is mathematically a
    point reflection, and a point reflection of a rectangle is PIXEL-IDENTICAL to some specific
    translation of that same rectangle (both preserve the rectangle's own width and height,
    landing it at a new position; nothing about the result distinguishes "this rotated" from
    "this slid over"). The test proved a box moved, not that Gmail rotates anything, and its
    "supported" verdict shipped as a false positive: the real digest went out rotated, and every
    rotated element in the real send measured 0.000deg.

    This version uses a genuine dimension swap instead, which NO translation can produce (a
    translation always preserves a shape's own width and height exactly): a long, thin bar
    (40x6) rotated 90deg about its own center (the CSS default transform-origin, so nothing
    about the origin needs separate verification either) becomes a thin, long bar (6x40) at the
    SAME center point. Geometry (CELL_PX_B=60, cell center at (30,30)): unrotated bar at
    margin(27,0,0,2) -> page box [2,42]x[27,33], own center (22,30) -- the cell-center sample
    point (30,30) sits exactly on this bar's vertical midline (safest possible spot, maximally
    far from both its top and bottom edges) and 12px clear of its right edge, so it reads GREEN
    if the transform is dropped entirely (fallback). Once genuinely rotated 90deg about (22,30),
    the SAME bar becomes 6 wide x 40 tall, still centered at (22,30) -> new box [19,25]x[10,50];
    the sample point (30,30) is now 5px clear OUTSIDE it on the x-axis, so it reads RED
    (container background) only if a real rotation happened. Both positive margins only --
    deliberately no negative-margin dependency, so this test can't be confounded by that
    separately-tested property."""
    html = (
        f'<div style="width:{CELL_PX_B}px;height:{CELL_PX_B}px;background:{_RED};overflow:hidden;">'
        f'<div style="width:40px;height:6px;margin:27px 0 0 2px;background:{_GREEN};'
        f'transform:rotate(90deg);"></div>'
        "</div>"
    )
    return _binary_test("transform_rotate", "transform:rotate (dimension-swap proof)", html, supported_hex=_RED, fallback_hex=_GREEN)


def _box_shadow_test() -> CssTest:
    """A small (20x20) base box sits at the cell's top-left corner, well clear of center. Its
    box-shadow is offset by (20,20) with zero blur/spread -- a crisp, solid copy of the box that,
    if box-shadow is honored, lands squarely on the cell's center with 10px margin on every side."""
    html = (
        f'<div style="width:{CELL_PX_B}px;height:{CELL_PX_B}px;background:{_RED};">'
        f'<div style="width:20px;height:20px;box-shadow:20px 20px 0 0 {_GREEN};"></div>'
        "</div>"
    )
    return _binary_test("box_shadow", "box-shadow (offset copy)", html)


def _border_radius_test() -> CssTest:
    """A green square's near (top-left) corner sits 8px from the cell's center by design, so an
    UNROUNDED sharp corner comfortably covers the center. Only the near corner is rounded (the
    4-value shorthand `border-radius:{R}px 0 0 0` -- a uniform radius on all four corners of a
    box this large would let the OTHER three corners' arcs interact in ways that don't reduce to
    simple distance-from-one-point math, which is exactly what broke the first version of this
    test against a real Chromium check). Geometry (CELL_PX_B=60): box 45x45 at margin(22,0,0,22)
    -> page near-corner (22,22); local point (8,8) [the true cell center, in this box's own
    coordinates] needs distance-from-the-arc-center > R to be excluded once rounded. With R=40,
    arc center is local (40,40); distance from (8,8) to (40,40) = 32*sqrt(2) =~ 45.25 > 40, so a
    genuinely rounded corner excludes the center (supported) with ~5px margin, while the
    unrounded case has the center 8px inside the box (fallback, still covered). Verdicts are
    inverted from the other tests -- rounding REMOVES coverage rather than adding it -- so
    `references` stores the mapping explicitly rather than assuming a global green-means-yes
    convention."""
    html = (
        f'<div style="width:{CELL_PX_B}px;height:{CELL_PX_B}px;background:{_RED};">'
        f'<div style="width:45px;height:45px;margin:22px 0 0 22px;background:{_GREEN};border-radius:40px 0 0 0;"></div>'
        "</div>"
    )
    return _binary_test("border_radius", "border-radius (corner-cut reveal)", html, supported_hex=_RED, fallback_hex=_GREEN)


def _linear_gradient_test() -> CssTest:
    """`background:RED` then `background:linear-gradient(...)` in the same declaration block --
    standard CSS cascade means an unparseable second value is simply dropped, leaving the first
    in effect. The gradient's hard color-stop sits at 40%, so the cell's center (50%) falls
    comfortably inside the green portion with real margin rather than sitting on the stop edge."""
    html = (
        f'<div style="width:{CELL_PX_B}px;height:{CELL_PX_B}px;'
        f'background:{_RED};background:linear-gradient(to right, transparent 40%, {_GREEN} 40%);"></div>'
    )
    return _binary_test("linear_gradient", "linear-gradient (background fallback chain)", html)


def _radial_gradient_shorthand_test() -> CssTest:
    """Defect candidate: email.py's `.page` background is the EXACT shorthand tested here --
    `background:{color} radial-gradient(...) position/size` in one declaration. If Gmail's
    sanitizer rejects the whole declaration for using a function it doesn't parse, `.page` loses
    its base cream color too, not just the dot pattern -- falling back to the RED declared
    before it here, GREEN before it in the real page (well, #fdfdfb-ish sheet white -- RED here
    is just the probe's own visible failure marker)."""
    html = (
        f'<div style="width:{CELL_PX_B}px;height:{CELL_PX_B}px;background:{_RED};'
        f'background:{_GREEN} radial-gradient(#00000012 1px, transparent 1px) 0 0/14px 14px;"></div>'
    )
    return _binary_test("radial_gradient_shorthand", "background shorthand + radial-gradient (defect candidate)", html)


def _radial_gradient_split_test() -> CssTest:
    """Control for the shorthand test above: the same declaration split into separate
    background-color / background-image / background-position / background-size properties.
    If this comes back `supported` while the shorthand test comes back `fallback`, that is
    direct evidence email.py's `.page` should switch to the split form."""
    html = (
        f'<div style="width:{CELL_PX_B}px;height:{CELL_PX_B}px;background:{_RED};'
        f'background-color:{_GREEN};background-image:radial-gradient(#00000012 1px, transparent 1px);'
        f'background-position:0 0;background-size:14px 14px;"></div>'
    )
    return _binary_test("radial_gradient_split", "background-color/-image split (defect candidate control)", html)


def _style_block_bare_test() -> CssTest:
    """Tests whether a `<style>` block in `<head>` is parsed at all, independent of specificity:
    the readout child has NO inline background of its own, relying purely on a class rule."""
    html = (
        f'<div style="width:{CELL_PX_B}px;height:{CELL_PX_B}px;background:{_RED};">'
        f'<div class="es-style-bare" style="width:{CELL_PX_B}px;height:{CELL_PX_B}px;"></div>'
        "</div>"
    )
    return _binary_test("style_block_bare", "&lt;style&gt; block parses at all", html)


def _style_important_over_inline_test() -> CssTest:
    """The exact mechanism email.py's real dark-mode block depends on: a stylesheet rule with
    `!important` overriding a per-instance inline style. If either the `<style>` block is
    stripped or `!important` isn't honored over inline, the inline red wins instead."""
    html = (
        f'<div class="es-style-important" style="width:{CELL_PX_B}px;height:{CELL_PX_B}px;background:{_RED};"></div>'
    )
    return _binary_test("style_important_over_inline", "!important class rule beats inline style", html)


_STYLE_BLOCK = (
    ".es-style-bare{background:#00FF00;}"
    ".es-style-important{background:#00FF00 !important;}"
)


def probe_b_tests() -> list[CssTest]:
    return [
        _display_flex_test(),
        _display_grid_test(),
        _float_test(),
        _position_absolute_test(),
        _negative_margin_test(),
        _transform_rotate_test(),
        _box_shadow_test(),
        _border_radius_test(),
        _linear_gradient_test(),
        _radial_gradient_shorthand_test(),
        _radial_gradient_split_test(),
        _style_block_bare_test(),
        _style_important_over_inline_test(),
    ]


@dataclass(frozen=True)
class CssTestGrid:
    name: str
    rows: int
    cols: int
    tests: list[CssTest]

    def __post_init__(self) -> None:
        if len(self.tests) != self.rows * self.cols:
            raise ValueError(
                f"grid {self.name!r}: {len(self.tests)} tests for a "
                f"{self.rows}x{self.cols} grid (need {self.rows * self.cols})"
            )

    def test_at(self, row: int, col: int) -> CssTest:
        return self.tests[row * self.cols + col]


def probe_b_grids() -> list[CssTestGrid]:
    tests = probe_b_tests()
    return [CssTestGrid("css_support", rows=len(tests), cols=1, tests=tests)]


def _css_test_grid_table_html(grid: CssTestGrid) -> str:
    cells = [_readout_td(grid.test_at(r, 0).html, cell_px=CELL_PX_B) for r in range(grid.rows)]
    return _frame_table_html(grid.rows, grid.cols, cells, cell_px=CELL_PX_B)


def render_probe_b() -> str:
    """Full standalone HTML document for the CSS-support-matrix probe. One column, one row per
    test, each labeled -- readable top-to-bottom next to whatever renders. `<style>` lives in
    <head> as normal (two of the tests specifically depend on it surviving there)."""
    grid = probe_b_grids()[0]
    # A spacer row matching the readout table's own top frame row, so the label column's rows
    # line up with their corresponding readout row -- purely for a human scanning the source;
    # extraction never looks at this column at all.
    spacer_row = f'<tr><td height="{CELL_PX_B}" style="height:{CELL_PX_B}px;line-height:0;font-size:0;">&nbsp;</td></tr>'
    label_rows = spacer_row + "".join(
        f'<tr><td height="{CELL_PX_B}" style="height:{CELL_PX_B}px;padding:4px 8px;'
        f'font-family:monospace;font-size:11px;color:#333;vertical-align:middle;">'
        f'{r:02d} &middot; {grid.test_at(r, 0).id}<br>'
        f'<span style="color:#777;">{grid.test_at(r, 0).label}</span></td></tr>'
        for r in range(grid.rows)
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Telogify emailsim -- Probe B (CSS support)</title>
<style>{_STYLE_BLOCK}</style>
</head>
<body style="margin:0;padding:20px;background:#ffffff;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
<td style="vertical-align:top;">{_css_test_grid_table_html(grid)}</td>
<td style="vertical-align:top;"><table role="presentation" cellpadding="0" cellspacing="0">{label_rows}</table></td>
</tr></table>
</body>
</html>"""


# ---------------------------------------------------------------------------------------------
# Probe E: does an image's own pixel content survive Gmail's dark-mode color rewriting where the
# same color expressed as CSS does not? Measured directly on 2026-08-02 for one case (the hosted
# favicon.svg's baked-in red stayed exact while CSS color/background of the same red inverted) --
# this probe checks whether that holds for every practical way the digest could carry a color as
# an image, using self-contained data-URI PNGs (no deploy/hosting needed to test it).
#
# Reuses Probe A's exact extraction path: each technique is a GridSpec, ground truth is the sent
# hex, extract_grid/SwatchMeasurement.delta (extract.py) need no changes since they only care
# about a magenta-framed table of cells and never look at what's inside a cell beyond its
# rendered color at the sample point.
# ---------------------------------------------------------------------------------------------

# The worst measured dark-mode offender (Probe A, 2026-08-01): relative luminance 0.698, the
# furthest of any digest color above Gmail's ~0.235 inversion fixed point, collapsing to
# #074231/1.28:1 via CSS. If any image technique preserves it, that is the one worth building the
# digest's color-carrying elements on.
PROBE_E_COLOR = "#27F4D2"


def _solid_png_data_uri(hexval: str, width: int, height: int) -> str:
    """A minimal solid-color PNG, hand-built (stdlib zlib/struct only, no image library needed
    just to generate a probe asset) and inlined as a data: URI so this probe needs no hosting."""
    r, g, b = int(hexval[1:3], 16), int(hexval[3:5], 16), int(hexval[5:7], 16)
    raw = b"".join(b"\x00" + bytes((r, g, b)) * width for _ in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _img_swatch_td(hexval: str, cell_px: int = CELL_PX) -> str:
    """Technique 1: a plain `<img>` element, the most direct way an email carries an image."""
    uri = _solid_png_data_uri(hexval, cell_px, cell_px)
    return (
        f'<td width="{cell_px}" height="{cell_px}" '
        f'style="width:{cell_px}px;height:{cell_px}px;padding:0;margin:0;border:0;font-size:0;line-height:0;">'
        f'<img src="{uri}" width="{cell_px}" height="{cell_px}" alt="" '
        f'style="display:block;width:{cell_px}px;height:{cell_px}px;border:0;"></td>'
    )


def _css_bg_image_swatch_td(hexval: str, cell_px: int = CELL_PX) -> str:
    """Technique 2: CSS `background-image` on the cell itself -- the mechanism the pace-spread
    swatches/bars would need if rebuilt as images without changing their markup shape."""
    uri = _solid_png_data_uri(hexval, cell_px, cell_px)
    return (
        f'<td width="{cell_px}" height="{cell_px}" '
        f'style="width:{cell_px}px;height:{cell_px}px;padding:0;margin:0;border:0;font-size:0;line-height:0;'
        f'background-image:url({uri});background-size:{cell_px}px {cell_px}px;">&nbsp;</td>'
    )


def _td_background_attr_swatch_td(hexval: str, cell_px: int = CELL_PX) -> str:
    """Technique 3: the old-school HTML `background=` attribute on `<td>` -- a distinct code path
    from CSS `background-image` in some mail clients' sanitizers, worth ruling in or out on its
    own rather than assuming it behaves like technique 2."""
    uri = _solid_png_data_uri(hexval, cell_px, cell_px)
    return (
        f'<td width="{cell_px}" height="{cell_px}" background="{uri}" '
        f'style="width:{cell_px}px;height:{cell_px}px;padding:0;margin:0;border:0;font-size:0;line-height:0;">&nbsp;</td>'
    )


def _bg_image_with_text_swatch_td(hexval: str, cell_px: int = CELL_PX) -> str:
    """Technique 4: background-image with real, live (selectable) text on top -- the construction
    behind the emails the user described, real text over an exact-color background. Text sits in
    the top-left corner; the grid's own sample point (this cell's true center, per
    extract.py's `_cell_center`) stays clear of every glyph by design, so it measures the
    background image's own surviving color, not text or its anti-aliasing."""
    uri = _solid_png_data_uri(hexval, cell_px, cell_px)
    return (
        f'<td width="{cell_px}" height="{cell_px}" '
        f'style="width:{cell_px}px;height:{cell_px}px;padding:0;margin:0;border:0;'
        f'background-image:url({uri});background-size:{cell_px}px {cell_px}px;">'
        f'<div style="font-family:Arial,sans-serif;font-size:9px;color:#fff;padding:2px 0 0 2px;">Aa</div></td>'
    )


_PROBE_E_TECHNIQUES: list[tuple[str, Callable[[str, int], str]]] = [
    ("img_solid_color", _img_swatch_td),
    ("css_background_image", _css_bg_image_swatch_td),
    ("td_background_attr", _td_background_attr_swatch_td),
    ("background_image_with_text", _bg_image_with_text_swatch_td),
]


def probe_e_grids() -> list[GridSpec]:
    """One 1x1 grid per technique, all carrying the same diagnostic color -- reuses GridSpec/
    extract_grid unchanged; only the cell HTML (image-based, not a flat CSS background) differs
    from Probe A."""
    return [GridSpec(name, rows=1, cols=1, swatches=[PROBE_E_COLOR]) for name, _ in _PROBE_E_TECHNIQUES]


def render_probe_e() -> str:
    """Full standalone HTML document for the image-color-survival probe. Grids stack vertically,
    same layout convention as render_probe_a, so locate_frames' top-to-bottom ordering lines up
    with probe_e_grids() the same way."""
    sections = []
    for name, cell_fn in _PROBE_E_TECHNIQUES:
        table = _frame_table_html(1, 1, [cell_fn(PROBE_E_COLOR, CELL_PX)], cell_px=CELL_PX)
        caption = f"{name} &middot; {PROBE_E_COLOR}"
        sections.append(
            '<div style="margin-bottom:40px;">'
            f'<p style="font-family:monospace;font-size:11px;color:#333;margin:0 0 8px;">{caption}</p>'
            f"{table}"
            "</div>"
        )
    body = "".join(sections)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Telogify emailsim -- Probe E (image color survival)</title>
</head>
<body style="margin:0;padding:20px;background:#ffffff;">
{body}
</body>
</html>"""
