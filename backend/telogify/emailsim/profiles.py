"""Named client/theme profiles: what applying a profile to real HTML means, backed only by
measured data -- see darkmode.py and support.py.

Desktop Gmail is deliberately absent here. Its dark-mode toggle was confirmed inert on the
tested account (every desktop screenshot read as light regardless of macOS appearance -- see
the emailsim plan), so there is no dark transform to model there, and desktop light-mode
fidelity was already independently confirmed by direct comparison against a real screenshot
(2026-08-01) with no simulation needed. Adding a `gmail-desktop-light` profile that's just an
identity color transform plus an unverified support matrix would imply more confidence than the
evidence actually supports, so it is left out rather than guessed.
"""

from __future__ import annotations

from dataclasses import dataclass

from telogify.emailsim.darkmode import ColorTransform
from telogify.emailsim.support import GMAIL_IOS_SUPPORT


# Measured 2026-08-02 from a real Gmail iOS screenshot (920px-wide capture), using the
# pace-spread `.swatch` -- a fixed 14x14 CSS px square regardless of content/data, the cleanest
# available reference since it can't be thrown off by font metrics the way text extents can. The
# swatch measured as a perfectly square 25x25px blob (both dimensions agreeing independently is
# the internal-consistency check that makes this trustworthy): scale = 25/14 = 1.79,
# viewport = 920 / 1.79 = 514px. Earlier session claims of "460px" and other ad-hoc pixel-scan
# attempts at other elements (border thickness, text width) gave inconsistent, noisier numbers
# and should not be trusted over this one. Not device-logical-width math (920px / a DPR of 2 or
# 3 doesn't cleanly match any real iPhone's point width either) -- Gmail's in-app webview likely
# renders HTML mail at its own fixed internal width rather than the device's own CSS viewport.
GMAIL_IOS_VIEWPORT_PX = 514


@dataclass(frozen=True)
class Profile:
    name: str
    color_transform: ColorTransform | None  # None means colors are left unchanged (light mode)
    support: dict[str, bool]
    viewport_width: int | None = None  # CSS px to render/screenshot at for this profile, if known


def gmail_ios_light() -> Profile:
    return Profile(
        name="gmail-ios-light", color_transform=None, support=GMAIL_IOS_SUPPORT,
        viewport_width=GMAIL_IOS_VIEWPORT_PX,
    )


def gmail_ios_dark() -> Profile:
    return Profile(
        name="gmail-ios-dark", color_transform=ColorTransform.fit(), support=GMAIL_IOS_SUPPORT,
        viewport_width=GMAIL_IOS_VIEWPORT_PX,
    )


_PROFILE_BUILDERS = {
    "gmail-ios-light": gmail_ios_light,
    "gmail-ios-dark": gmail_ios_dark,
}


def get_profile(name: str) -> Profile:
    try:
        return _PROFILE_BUILDERS[name]()
    except KeyError:
        raise KeyError(f"unknown emailsim profile {name!r} (available: {sorted(_PROFILE_BUILDERS)})") from None
