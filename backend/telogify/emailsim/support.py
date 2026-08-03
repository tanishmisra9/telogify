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
  - Negative margins WERE claimed to work here. See the 2026-08-02 correction below: they do not.
  - border-radius does NOT work.
  - box-shadow WAS claimed to work here, contradicting email.py's existing comment that it's
    dead on iOS. See the 2026-08-02 correction below: it does not.
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

CORRECTION (2026-08-02, transform_rotate): was WRONG. It shipped as True, and the digest went out
rotated -- but every rotated element in the real send measured **0.000 degrees** (the stamp's
inline `rotate(-4deg)` and the section-title chips' stylesheet `rotate(1.5deg)`, both measured via
top-edge slope on the actual screenshots). The original probe's "supported" branch used
`rotate(180deg)` around an off-center transform-origin -- which is geometrically identical to a
pure translation, the one degenerate case where "the box rotated" and "something else moved the
box" produce the same pixels. It proved a box moved, not that Gmail rotates anything.

CORRECTION (2026-08-02, box_shadow): also WRONG, found by re-checking every remaining verdict
against the same real send rather than assuming they were fine because the rotation bug was an
isolated fluke. Measured directly: the headline block's border is exactly 5px thick at its
bottom-right corner (x=790, y=702-706) -- the one place a 7px-offset shadow computationally MUST
add ~12px of extra dark region if box-shadow is honored. There is none; 5px is exactly what a
plain 3px CSS border scales to at this capture's 1.79x. A practice tile's corner (smaller, 3.5px
offset) showed the same: a single flat border line, no depth. Every panel in the redesigned
digest relies on box-shadow for its visual depth, so this is a second real regression the same
class of send shipped with, not a one-off.

CORRECTION (2026-08-02, negative_margin): also WRONG. email.py used a negative margin to pull a
panel-label chip (e.g. WINNER) back through its card's own padding to sit flush at the top-left
corner, verified at exactly 0px in Chromium (a real Playwright measurement, not eyeballed) --
but a real Gmail screenshot showed a visible gap remained, the negative margin not honored. Fixed
by restructuring instead of relying on the property at all: the outer card's padding drops to 0
so the label sits flush in normal flow with no margin trick needed, and an inner wrapper div
around the rest of the content (heading/body) carries the padding instead. Third false positive
from this matrix, all found the same way -- checking a composed real send against what the
isolated Probe B test predicted for it.

All three false positives came from Probe B testing single properties in isolation with synthetic
geometry and never comparing a composed render against reality -- see the emailsim plan. Every
remaining `True` verdict in this matrix (both gradients, the two <style> tests, display_flex)
still needs the same direct re-check before being trusted for a design decision.
"""

from __future__ import annotations

GMAIL_IOS_SUPPORT: dict[str, bool] = {
    "display_flex": True,
    "display_grid": False,
    "float": False,
    "position_absolute": False,
    "negative_margin": False,  # corrected 2026-08-02, see module docstring
    "transform_rotate": False,  # corrected 2026-08-02, see module docstring
    "box_shadow": False,  # corrected 2026-08-02, see module docstring
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
