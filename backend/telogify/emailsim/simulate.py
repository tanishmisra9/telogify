"""Applies a measured Profile to real digest HTML: color substitution via the fitted dark-mode
transform, and stripping of CSS declarations the profile's support matrix says the client
doesn't honor. Returns modified HTML meant to be rendered by a real, standards-compliant browser
(Chromium via playwright-cli) -- this module does not render anything itself.

Stripping an unsupported declaration and letting a real renderer lay out the rest is deliberately
more honest than hand-reimplementing layout without a browser: a client that ignores
`border-radius` renders identically to a browser given the same HTML with that declaration
simply absent, so removing it and rendering normally is not an approximation of that behavior,
it IS that behavior (for the color/support model this package covers -- see the emailsim plan's
stated ceiling on what it does and doesn't model).
"""

from __future__ import annotations

import re

from telogify.emailsim.profiles import Profile

# Matches 6-digit hex first (with a lookahead guard so it never partially matches the first 6
# digits of an 8-digit alpha hex like #0a0a0a55, which is deliberately left untouched -- no
# measured data covers alpha colors), falling back to 3-digit shorthand (#fff, #000) which
# email.py's white-on-black chips (.section-title, .verdict, .lbl, .nb-num) actually use. Missing
# this the first time round left `color:#fff` untransformed while its sibling 6-digit background
# (`#0a0a0a` -> near-white) did transform, turning white-on-black chips into white-on-white --
# caught by rendering the result, not by inspecting the code.
_HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{6}(?![0-9a-fA-F])|[0-9a-fA-F]{3}(?![0-9a-fA-F]))")


def _normalize_hex(short_or_full: str) -> str:
    h = short_or_full.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return f"#{h}"

# test_id -> a regex matching the CSS declaration(s) that Probe B test represents. Only
# properties actually used somewhere in the digest need an entry here to have any real effect;
# entries for properties the digest never uses are harmless no-ops.
_PROPERTY_STRIP_PATTERNS: dict[str, str] = {
    "display_grid": r"display\s*:\s*grid\s*;?",
    "float": r"float\s*:\s*(left|right)\s*;?",
    "position_absolute": r"position\s*:\s*absolute\s*;?",
    "border_radius": r"border-radius\s*:\s*[^;\"']+;?",
}


def apply(html: str, profile: Profile) -> str:
    out = html
    if profile.color_transform is not None:
        out = _HEX_RE.sub(lambda m: profile.color_transform.apply(_normalize_hex(m.group(0))), out)
    for test_id, is_supported in profile.support.items():
        if is_supported:
            continue
        pattern = _PROPERTY_STRIP_PATTERNS.get(test_id)
        if pattern is None:
            continue
        out = re.sub(pattern, "", out, flags=re.IGNORECASE)
    return out
