"""Tests for telogify.emailsim.profiles and telogify.emailsim.simulate.

apply() is tested against small synthetic HTML snippets rather than the real digest -- the
digest's own rendering is already covered by test_email.py, and these tests only need to prove
apply()'s two mechanical transforms (hex substitution, unsupported-property stripping) work
correctly in isolation.
"""

import pytest

from telogify.emailsim.darkmode import ColorTransform
from telogify.emailsim.profiles import Profile, get_profile
from telogify.emailsim.simulate import apply


def test_get_profile_gmail_ios_light_has_no_color_transform():
    profile = get_profile("gmail-ios-light")
    assert profile.color_transform is None


def test_get_profile_gmail_ios_dark_has_a_color_transform():
    profile = get_profile("gmail-ios-dark")
    assert isinstance(profile.color_transform, ColorTransform)


def test_get_profile_raises_on_unknown_name():
    with pytest.raises(KeyError):
        get_profile("outlook-desktop-dark")


def test_apply_light_profile_leaves_colors_unchanged():
    profile = get_profile("gmail-ios-light")
    html = '<div style="background:#0a0a0a;color:#fff;"></div>'
    assert apply(html, profile) == html


def test_apply_dark_profile_substitutes_a_measured_color():
    profile = get_profile("gmail-ios-dark")
    html = '<div style="background:#000000;"></div>'
    result = apply(html, profile)
    assert "#000000" not in result
    assert profile.color_transform.apply("#000000") in result


def test_apply_dark_profile_expands_and_substitutes_3_digit_hex():
    # email.py's white-on-black chips (.section-title, .verdict, .lbl, .nb-num) use the 3-digit
    # shorthand `#fff` for their text color -- missing this left chips white-on-white the first
    # time, since the sibling 6-digit `#0a0a0a` background transformed but `#fff` didn't.
    profile = get_profile("gmail-ios-dark")
    html = '<span style="background:#0a0a0a;color:#fff;">WINNER</span>'
    result = apply(html, profile)
    assert "#fff" not in result
    assert profile.color_transform.apply("#ffffff") in result


def test_apply_dark_profile_section_title_chip_stays_high_contrast():
    # regression: background and text must not converge to near-identical lightness.
    profile = get_profile("gmail-ios-dark")
    html = '<span style="background:#0a0a0a;color:#fff;padding:6px 14px;">SUNDAY&rsquo;S FRONT RUNNERS</span>'
    result = apply(html, profile)
    import re

    bg_hex, text_hex = re.findall(r"#[0-9a-fA-F]{6}", result)
    bg_luminance = sum(int(bg_hex[i : i + 2], 16) for i in (1, 3, 5)) / 3
    text_luminance = sum(int(text_hex[i : i + 2], 16) for i in (1, 3, 5)) / 3
    assert abs(bg_luminance - text_luminance) > 80


def test_apply_dark_profile_leaves_8_digit_alpha_hex_untouched():
    profile = get_profile("gmail-ios-dark")
    html = '<td style="border-bottom:1px dashed #0a0a0a55;"></td>'
    assert "#0a0a0a55" in apply(html, profile)


def test_apply_strips_unsupported_border_radius():
    support = {"border_radius": False}
    profile = Profile(name="test", color_transform=None, support=support)
    html = '<span class="nb-num" style="border-radius:3px;background:#fff;">01</span>'
    result = apply(html, profile)
    assert "border-radius" not in result
    assert "background:#fff" in result


def test_apply_keeps_supported_properties():
    support = {"border_radius": True}
    profile = Profile(name="test", color_transform=None, support=support)
    html = '<span style="border-radius:3px;"></span>'
    assert "border-radius:3px" in apply(html, profile)


def test_apply_unsupported_property_not_used_in_html_is_a_no_op():
    support = {"float": False}
    profile = Profile(name="test", color_transform=None, support=support)
    html = "<div>no float here</div>"
    assert apply(html, profile) == html


def test_apply_strips_transform_rotate_by_default_on_the_gmail_ios_profile():
    # measured 2026-08-02: real rotated elements come back at 0.000deg. gmail-ios-{light,dark}'s
    # support matrix must mark transform_rotate unsupported and this must actually strip it.
    profile = get_profile("gmail-ios-light")
    html = '<div style="transform:rotate(-4deg);background:red;"></div>'
    result = apply(html, profile)
    assert "transform" not in result
    assert "background:red" in result


def test_apply_always_strips_the_webfont_link_regardless_of_profile():
    # Gmail never fetches external stylesheets -- unconditional, not keyed to any support-matrix
    # entry, so this must strip even for a profile with no unsupported properties at all.
    profile = Profile(name="test", color_transform=None, support={})
    html = (
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link href="https://fonts.googleapis.com/css2?family=Archivo+Black&display=swap" rel="stylesheet">'
        "<title>kept</title>"
    )
    result = apply(html, profile)
    assert "fonts.googleapis.com" not in result
    assert "<title>kept</title>" in result


def test_apply_dark_profile_does_not_transform_colors_inside_img_tags():
    # image pixels bypass Gmail's color rewriting entirely (measured 2026-08-02: a hosted SVG's
    # internal red stayed exact while CSS-colored reds around it inverted), so an <img>'s own
    # markup must never be treated as authored light-mode CSS the way an inline style is.
    profile = get_profile("gmail-ios-dark")
    html = '<img src="https://example.com/logo.svg" alt="#0a0a0a mark"><div style="color:#0a0a0a;"></div>'
    result = apply(html, profile)
    assert '<img src="https://example.com/logo.svg" alt="#0a0a0a mark">' in result
    assert "color:#0a0a0a" not in result
