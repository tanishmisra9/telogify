"""Pixel extraction: a screenshot -> measured RGB per swatch.

Every sample coordinate is computed from a *located* grid's own measured pixel size (never a
hardcoded coordinate, never an assumption about zoom or device pixel ratio): `locate_frames`
finds each probe grid's magenta border as a connected blob, and `_cell_center` divides that
blob's own bounding box by the grid's known (rows+2, cols+2) cell count from `probe.py`. If the
screenshot is scaled, cropped consistently, or captured at a different device pixel ratio than
another, this still lands on the right pixel as long as the whole grid is visible and undistorted.

Deliberately conservative about trusting a screenshot: `locate_frames` raises rather than
guessing when it doesn't find exactly the expected number of grids, and `draw_debug_overlay`
always produces an annotated image showing exactly where every sample was taken, meant to be
eyeballed before any measurement is treated as real. Measure, then verify the measurement.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from telogify.emailsim.probe import FRAME_COLOR, CssTestGrid, GridSpec


def hex_to_rgb(hexval: str) -> tuple[int, int, int]:
    h = hexval.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = (int(round(c)) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


@dataclass(frozen=True)
class GridBox:
    """Pixel-space bounding box (screenshot coordinates) of a located grid's magenta frame,
    inclusive of the frame cells themselves."""

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


def load_image(path: str | Path) -> np.ndarray:
    return np.array(Image.open(path).convert("RGB"))


def locate_frames(
    image: np.ndarray, target_hex: str = FRAME_COLOR, tol: int = 40, min_area: int = 500
) -> list[GridBox]:
    """Finds every separate connected blob of pixels close to target_hex and returns their
    bounding boxes ordered top-to-bottom -- which matches the vertical stacking order
    `probe.render_probe_a` renders grids in, so callers can `zip()` this directly against
    `probe_a_grids()`. Components smaller than min_area are dropped as noise (an isolated
    anti-aliased pixel near a swatch edge can register as near-magenta by chance)."""
    target = np.array(hex_to_rgb(target_hex), dtype=np.int32)
    dist = np.sqrt(((image.astype(np.int32) - target) ** 2).sum(axis=-1))
    mask = dist <= tol

    labeled, _ = ndimage.label(mask)
    boxes = []
    for slice_y, slice_x in ndimage.find_objects(labeled):
        if slice_y is None:
            continue
        area = (slice_y.stop - slice_y.start) * (slice_x.stop - slice_x.start)
        if area < min_area:
            continue
        boxes.append(GridBox(left=slice_x.start, top=slice_y.start, right=slice_x.stop, bottom=slice_y.stop))
    boxes.sort(key=lambda b: b.top)
    return boxes


def _cell_center(box: GridBox, grid: GridSpec | CssTestGrid, row: int, col: int) -> tuple[float, float]:
    """The frame's measured box spans (cols+2) x (rows+2) cells (probe.py's one-cell magenta
    border on every side). Dividing the box's own measured width/height -- not the nominal
    CELL_PX -- by that count gives the real screenshot px-per-cell, so this is correct even if
    the screenshot isn't 1:1 with CSS pixels."""
    px_per_col = box.width / (grid.cols + 2)
    px_per_row = box.height / (grid.rows + 2)
    cx = box.left + px_per_col * (col + 1.5)
    cy = box.top + px_per_row * (row + 1.5)
    return cx, cy


def sample_patch(image: np.ndarray, cx: float, cy: float, radius: int = 6) -> tuple[int, int, int]:
    """Median color of a (2*radius+1)-square patch centered on (cx, cy). Median rather than
    mean so a single stray anti-aliased pixel can't drag the result."""
    h, w = image.shape[:2]
    x0, x1 = max(0, int(cx) - radius), min(w, int(cx) + radius + 1)
    y0, y1 = max(0, int(cy) - radius), min(h, int(cy) + radius + 1)
    patch = image[y0:y1, x0:x1].reshape(-1, 3)
    return tuple(int(v) for v in np.median(patch, axis=0))


@dataclass(frozen=True)
class SwatchMeasurement:
    grid: str
    row: int
    col: int
    expected_hex: str
    measured_hex: str
    measured_rgb: tuple[int, int, int]

    @property
    def delta(self) -> float:
        """Euclidean RGB distance between what was sent and what was measured -- 0 for a
        perfect round-trip, large for an inverted or heavily shifted color."""
        a = np.array(hex_to_rgb(self.expected_hex), dtype=np.float64)
        b = np.array(self.measured_rgb, dtype=np.float64)
        return float(np.sqrt(((a - b) ** 2).sum()))


def extract_grid(image: np.ndarray, grid: GridSpec, box: GridBox) -> list[SwatchMeasurement]:
    out = []
    for r in range(grid.rows):
        for c in range(grid.cols):
            cx, cy = _cell_center(box, grid, r, c)
            rgb = sample_patch(image, cx, cy)
            out.append(SwatchMeasurement(grid.name, r, c, grid.swatch_at(r, c), rgb_to_hex(rgb), rgb))
    return out


def locate_and_extract(
    image: np.ndarray, grids: list[GridSpec], tol: int = 40
) -> dict[str, list[SwatchMeasurement]]:
    boxes = locate_frames(image, tol=tol)
    if len(boxes) != len(grids):
        raise ValueError(
            f"expected {len(grids)} probe grid(s), found {len(boxes)} magenta-framed region(s) "
            "in the screenshot -- check the crop, or that no other magenta-ish content is in "
            "frame, or adjust --tol"
        )
    return {grid.name: extract_grid(image, grid, box) for grid, box in zip(grids, boxes)}


def draw_debug_overlay(
    image: np.ndarray, grids: list[GridSpec] | list[CssTestGrid], boxes: list[GridBox]
) -> Image.Image:
    """Green frame box + a small marker at every sample point, so a human can confirm the
    extraction landed on the right pixels before any measurement is trusted."""
    img = Image.fromarray(image).convert("RGB")
    draw = ImageDraw.Draw(img)
    for grid, box in zip(grids, boxes):
        draw.rectangle([box.left, box.top, box.right, box.bottom], outline=(0, 255, 0), width=2)
        for r in range(grid.rows):
            for c in range(grid.cols):
                cx, cy = _cell_center(box, grid, r, c)
                draw.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], outline=(0, 255, 0), width=1)
    return img


@dataclass(frozen=True)
class CssTestVerdict:
    id: str
    label: str
    verdict: str  # "supported" | "fallback" | "ambiguous" (nearest-color classification)
    measured_rgb: tuple[int, int, int]
    references: list[tuple[str, str]]


def _nearest_reference(rgb: tuple[int, int, int], references: list[tuple[str, str]]) -> str:
    best_verdict, best_dist = "ambiguous", float("inf")
    measured = np.array(rgb, dtype=np.float64)
    for verdict, hexval in references:
        dist = float(np.sqrt(((measured - np.array(hex_to_rgb(hexval), dtype=np.float64)) ** 2).sum()))
        if dist < best_dist:
            best_dist, best_verdict = dist, verdict
    return best_verdict


def classify_css_tests(image: np.ndarray, grid: CssTestGrid, box: GridBox, radius: int = 4) -> list[CssTestVerdict]:
    """Reads each Probe B test cell the same way extract_grid reads a Probe A swatch (same
    `_cell_center`/`sample_patch` primitives, same magenta-frame geometry) but classifies the
    measured color against each test's own declared (verdict, hex) reference pairs instead of
    checking equality against one expected value -- there IS no single ground-truth color here,
    that's what's being determined. A smaller default sample radius than Probe A's (4 vs 6
    screenshot px) matches Probe B's tighter engineered margins on some tests (e.g.
    transform_rotate's ~5px clearance in CSS px)."""
    out = []
    for r in range(grid.rows):
        test = grid.test_at(r, 0)
        cx, cy = _cell_center(box, grid, r, 0)
        rgb = sample_patch(image, cx, cy, radius=radius)
        out.append(CssTestVerdict(test.id, test.label, _nearest_reference(rgb, test.references), rgb, test.references))
    return out


def locate_and_classify(image: np.ndarray, grids: list[CssTestGrid], tol: int = 40) -> dict[str, list[CssTestVerdict]]:
    boxes = locate_frames(image, tol=tol)
    if len(boxes) != len(grids):
        raise ValueError(
            f"expected {len(grids)} probe grid(s), found {len(boxes)} magenta-framed region(s) "
            "in the screenshot -- check the crop, or that no other magenta-ish content is in "
            "frame, or adjust --tol"
        )
    return {grid.name: classify_css_tests(image, grid, box) for grid, box in zip(grids, boxes)}
