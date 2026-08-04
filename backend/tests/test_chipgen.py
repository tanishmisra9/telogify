import io

from PIL import Image

from telogify.chipgen import measure_text_chip, render_text_chip_png


def test_measure_text_chip_grows_with_padding():
    bare_w, bare_h = measure_text_chip("GEORGE RUSSELL", font_size=28)
    padded_w, padded_h = measure_text_chip("GEORGE RUSSELL", font_size=28, padding=(3, 10, 3, 10))
    assert padded_w == bare_w + 20
    assert padded_h == bare_h + 6


def test_render_text_chip_png_is_valid_png_at_retina_scale():
    width, height = measure_text_chip("01", font_size=12, padding=(4, 9, 4, 9))
    png = render_text_chip_png(
        "01", font_size=12, text_color="#0a0a0a", bg_color="#27F4D2",
        padding=(4, 9, 4, 9), border_radius=3,
    )
    img = Image.open(io.BytesIO(png))
    assert img.format == "PNG"
    # scale=3 by default -- the served file is retina-sharp, displayed at the logical size
    assert img.size == (width * 3, height * 3)


def test_render_text_chip_png_transparent_background_has_alpha():
    png = render_text_chip_png("GEORGE RUSSELL", font_size=28, text_color="#27F4D2")
    img = Image.open(io.BytesIO(png))
    assert img.mode == "RGBA"
    # top-left corner is outside any glyph -- must stay fully transparent, not filled
    assert img.getpixel((0, 0))[3] == 0
