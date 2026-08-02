"""Measured Gmail iOS app CSS support matrix.

GMAIL_IOS_SUPPORT is real measured data from Probe B (13 CSS-property reveal tests), captured
from Gmail iOS app screenshots on 2026-08-01, light and dark theme both. Light and dark agreed on
every single test, which is expected -- CSS *support* (whether a property is honored at all) is
a layout/parsing question, not a color question, so the same client shouldn't parse HTML/CSS
differently just because it's showing dark-inverted colors.

Findings that correct prior assumptions documented as comments in email.py (see the emailsim
plan's "three defect candidates" section, and beyond -- Probe B ended up testing more than those
three once built):
  - display:flex WORKS. display:grid, float, and position:absolute do NOT.
  - Negative margins work.
  - border-radius does NOT work.
  - box-shadow DOES work -- contradicts email.py's existing comment claiming it's dead on iOS.
  - linear-gradient, and BOTH radial-gradient forms (the shorthand email.py's `.page` actually
    uses, and the split control), all work -- the shorthand's base color is not silently
    dropped, so that defect candidate also does not apply on this client.
  - <style> blocks parse, and !important there correctly overrides inline styles -- the exact
    mechanism the real dark-mode block in email.py depends on is confirmed working.
  - clip-path does NOT work (added 2026-08-02 via a standalone one-off probe, same red/green
    reveal technique as the rest of Probe B, not part of the original 13 -- verified in Chromium
    first, then measured across three real surfaces at once: Gmail desktop web light, Gmail iOS
    light, and Gmail iOS dark, all three reading the "ignored" red). This settles the comp's
    torn-paper masthead strip (clip-path polygon()): it can't be built this way, and confirms
    the strip's pre-existing absence from the digest was the right call, not a missed detail.

CORRECTION (2026-08-02): transform_rotate was WRONG. It shipped as True, and the digest went out
rotated -- but every rotated element in the real send measured **0.000 degrees** (the stamp's
inline `rotate(-4deg)` and the section-title chips' stylesheet `rotate(1.5deg)`, both measured via
top-edge slope on the actual screenshots). The original probe's "supported" branch used
`rotate(180deg)` around an off-center transform-origin -- which is geometrically identical to a
pure translation, the one degenerate case where "the box rotated" and "something else moved the
box" produce the same pixels. It proved a box moved, not that Gmail rotates anything. Every other
verdict in this file needs re-checking against a real composed render, not just a synthetic
Probe B cell, before being trusted again.
"""

from __future__ import annotations

GMAIL_IOS_SUPPORT: dict[str, bool] = {
    "display_flex": True,
    "display_grid": False,
    "float": False,
    "position_absolute": False,
    "negative_margin": True,
    "transform_rotate": False,  # corrected 2026-08-02, see module docstring
    "box_shadow": True,
    "border_radius": False,
    "linear_gradient": True,
    "radial_gradient_shorthand": True,
    "radial_gradient_split": True,
    "style_block_bare": True,
    "style_important_over_inline": True,
    "clip_path": False,
}


def supported(test_id: str) -> bool:
    """Raises KeyError for an unknown test id rather than silently defaulting -- a typo'd id
    should fail loudly, not be treated as unsupported."""
    return GMAIL_IOS_SUPPORT[test_id]
