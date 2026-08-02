"""Pure-compute tests for telogify.emailsim.

test_round_trip_recovers_every_swatch_exactly is the real gate described in the emailsim plan:
if extraction can't recover known colors from a synthesized image, it has no business
interpreting a real Gmail screenshot. The synthesis in _synthesize_probe_a_image hand-draws the
exact geometry probe.py's HTML describes, entirely offline (no playwright, no DB, no network),
so this is a true round-trip of the measurement pipeline's own logic.
"""

import numpy as np
import pytest
from PIL import Image, ImageDraw

from telogify.emailsim.extract import (
    GridBox,
    classify_css_tests,
    draw_debug_overlay,
    hex_to_rgb,
    load_image,
    locate_and_classify,
    locate_and_extract,
    locate_frames,
    rgb_to_hex,
    sample_patch,
)
from telogify.emailsim.probe import (
    CELL_PX,
    CELL_PX_B,
    FRAME_COLOR,
    CssTestGrid,
    GridSpec,
    probe_a_grids,
    probe_b_grids,
    probe_b_tests,
    render_probe_a,
    render_probe_b,
)


def _synthesize_probe_a_image(grids: list[GridSpec], cell_px: int = CELL_PX, gap: int = 24) -> np.ndarray:
    """Hand-draws the same geometry probe.py's HTML describes -- a magenta frame one cell wide
    around each grid, solid swatch cells inside -- entirely offline. PIL's rectangle fill is an
    exact pixel fill with no anti-aliasing, so this is a noise-free ground truth."""
    widths = [(g.cols + 2) * cell_px for g in grids]
    heights = [(g.rows + 2) * cell_px for g in grids]
    canvas = Image.new("RGB", (max(widths) + 2 * gap, sum(heights) + gap * (len(grids) + 1)), "white")
    draw = ImageDraw.Draw(canvas)
    y = gap
    for grid, w, h in zip(grids, widths, heights):
        x0, y0 = gap, y
        draw.rectangle([x0, y0, x0 + w, y0 + h], fill=FRAME_COLOR)
        for r in range(grid.rows):
            for c in range(grid.cols):
                cx0 = x0 + (c + 1) * cell_px
                cy0 = y0 + (r + 1) * cell_px
                draw.rectangle([cx0, cy0, cx0 + cell_px, cy0 + cell_px], fill=grid.swatch_at(r, c))
        y += h + gap
    return np.array(canvas)


def test_round_trip_recovers_every_swatch_exactly():
    grids = probe_a_grids()
    image = _synthesize_probe_a_image(grids)

    results = locate_and_extract(image, grids)

    assert set(results) == {g.name for g in grids}
    total = 0
    for grid in grids:
        measurements = results[grid.name]
        assert len(measurements) == grid.rows * grid.cols
        for m in measurements:
            assert m.measured_hex == m.expected_hex.lower(), f"{grid.name}[{m.row}][{m.col}]"
            assert m.delta == 0
            total += 1
    assert total == sum(g.rows * g.cols for g in grids)


def test_round_trip_survives_uniform_rescale():
    """A screenshot won't be captured at exactly 1 CSS px == 1 image px (device pixel ratio,
    browser zoom). Extraction must still recover exact colors after uniform upscaling, since
    _cell_center derives px-per-cell from the located box's own measured size, not CELL_PX."""
    grids = probe_a_grids()
    image = _synthesize_probe_a_image(grids)
    scaled = Image.fromarray(image).resize((image.shape[1] * 2, image.shape[0] * 2), Image.NEAREST)
    scaled_array = np.array(scaled)

    results = locate_and_extract(scaled_array, grids)

    for grid in grids:
        for m in results[grid.name]:
            assert m.measured_hex == m.expected_hex.lower()


def test_locate_frames_orders_top_to_bottom():
    grids = probe_a_grids()
    image = _synthesize_probe_a_image(grids)
    boxes = locate_frames(image)
    assert len(boxes) == len(grids)
    tops = [b.top for b in boxes]
    assert tops == sorted(tops)


def test_locate_and_extract_raises_when_grid_count_mismatches():
    grids = probe_a_grids()
    image = _synthesize_probe_a_image(grids)
    with pytest.raises(ValueError, match=r"expected 2 probe grid\(s\), found 3"):
        locate_and_extract(image, grids[:2])


def test_grid_spec_validates_swatch_count():
    with pytest.raises(ValueError):
        GridSpec("bad", rows=2, cols=2, swatches=["#000000"])  # needs 4, gave 1


def test_grid_spec_swatch_at_is_row_major():
    grid = GridSpec("g", rows=2, cols=2, swatches=["#000000", "#111111", "#222222", "#333333"])
    assert grid.swatch_at(0, 0) == "#000000"
    assert grid.swatch_at(0, 1) == "#111111"
    assert grid.swatch_at(1, 0) == "#222222"
    assert grid.swatch_at(1, 1) == "#333333"


def test_hex_rgb_round_trip():
    for hexval in ["#000000", "#ffffff", "#E10600", "#27f4d2"]:
        assert rgb_to_hex(hex_to_rgb(hexval)) == hexval.lower()


def test_sample_patch_median_ignores_single_stray_pixel():
    image = np.full((20, 20, 3), 100, dtype=np.uint8)
    image[10, 10] = [255, 0, 0]  # one stray pixel at the sample center
    rgb = sample_patch(image, cx=10, cy=10, radius=6)
    assert rgb == (100, 100, 100)


def test_draw_debug_overlay_returns_image_same_size():
    grids = probe_a_grids()
    image = _synthesize_probe_a_image(grids)
    boxes = locate_frames(image)
    overlay = draw_debug_overlay(image, grids, boxes)
    assert overlay.size == (image.shape[1], image.shape[0])


def test_render_probe_a_is_a_standalone_document_with_every_swatch():
    html = render_probe_a()
    assert html.lower().startswith("<!doctype html>")
    grids = probe_a_grids()
    for grid in grids:
        for r in range(grid.rows):
            for c in range(grid.cols):
                assert grid.swatch_at(r, c) in html
    # frame cells: (rows+2)*(cols+2) per grid, swatch cells: rows*cols per grid
    expected_frame_cells = sum((g.rows + 2) * (g.cols + 2) - g.rows * g.cols for g in grids)
    assert html.count(FRAME_COLOR) == expected_frame_cells


def test_load_image_reads_rgb_array(tmp_path):
    path = tmp_path / "swatch.png"
    Image.new("RGB", (10, 10), "#123456").save(path)
    array = load_image(path)
    assert array.shape == (10, 10, 3)
    assert tuple(array[5, 5]) == (0x12, 0x34, 0x56)


# --------------------------------------------------------------------------------------------
# Probe B: the CSS support matrix. These tests exercise classify_css_tests' nearest-reference
# logic directly (painting each test's declared reference colors at the correct grid position),
# not real CSS rendering -- that side is verified separately by rendering render_probe_b()
# through a real browser and confirming every test reads "supported" against a full-CSS-support
# renderer (documented in each test function's own docstring in probe.py, where two tests'
# geometry was corrected after that exact check caught a wrong-direction assumption).
# --------------------------------------------------------------------------------------------


def _synthesize_css_test_image(grid: CssTestGrid, verdict: str, cell_px: int = CELL_PX_B, gap: int = 24) -> np.ndarray:
    """Paints grid.name's magenta frame with each cell filled by the reference color for
    `verdict` -- entirely bypassing real CSS/HTML rendering, to test classify_css_tests'
    classification logic in isolation."""
    w = (grid.cols + 2) * cell_px
    h = (grid.rows + 2) * cell_px
    canvas = Image.new("RGB", (w + 2 * gap, h + 2 * gap), "white")
    draw = ImageDraw.Draw(canvas)
    x0, y0 = gap, gap
    draw.rectangle([x0, y0, x0 + w, y0 + h], fill=FRAME_COLOR)
    for r in range(grid.rows):
        for c in range(grid.cols):
            test = grid.test_at(r, c)
            cx0 = x0 + (c + 1) * cell_px
            cy0 = y0 + (r + 1) * cell_px
            draw.rectangle([cx0, cy0, cx0 + cell_px, cy0 + cell_px], fill=test.hex_for(verdict))
    return np.array(canvas)


def test_classify_css_tests_recovers_every_supported_verdict():
    grids = probe_b_grids()
    grid = grids[0]
    image = _synthesize_css_test_image(grid, "supported")
    results = locate_and_classify(image, grids)
    for v in results[grid.name]:
        assert v.verdict == "supported", v.id


def test_classify_css_tests_recovers_every_fallback_verdict():
    grids = probe_b_grids()
    grid = grids[0]
    image = _synthesize_css_test_image(grid, "fallback")
    results = locate_and_classify(image, grids)
    for v in results[grid.name]:
        assert v.verdict == "fallback", v.id


def test_locate_and_classify_raises_on_mismatched_grid_count():
    grids = probe_b_grids()
    image = _synthesize_css_test_image(grids[0], "supported")
    with pytest.raises(ValueError, match=r"expected 2 probe grid\(s\), found 1"):
        locate_and_classify(image, grids + grids)


def test_css_test_grid_validates_test_count():
    with pytest.raises(ValueError):
        CssTestGrid("bad", rows=2, cols=1, tests=[probe_b_tests()[0]])  # needs 2, gave 1


def test_probe_b_tests_ids_are_unique():
    ids = [t.id for t in probe_b_tests()]
    assert len(ids) == len(set(ids))


def test_probe_b_tests_each_have_two_distinct_reference_colors():
    for test in probe_b_tests():
        colors = [hexval for _, hexval in test.references]
        assert len(colors) == len(set(colors)), test.id


def test_render_probe_b_is_a_standalone_document_containing_every_test():
    html = render_probe_b()
    assert html.lower().startswith("<!doctype html>")
    assert "<style>" in html
    for test in probe_b_tests():
        assert test.id in html
        assert test.html in html


def test_css_test_hex_for_raises_on_unknown_verdict():
    test = probe_b_tests()[0]
    with pytest.raises(KeyError):
        test.hex_for("ambiguous")
