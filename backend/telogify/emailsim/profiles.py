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


@dataclass(frozen=True)
class Profile:
    name: str
    color_transform: ColorTransform | None  # None means colors are left unchanged (light mode)
    support: dict[str, bool]


def gmail_ios_light() -> Profile:
    return Profile(name="gmail-ios-light", color_transform=None, support=GMAIL_IOS_SUPPORT)


def gmail_ios_dark() -> Profile:
    return Profile(name="gmail-ios-dark", color_transform=ColorTransform.fit(), support=GMAIL_IOS_SUPPORT)


_PROFILE_BUILDERS = {
    "gmail-ios-light": gmail_ios_light,
    "gmail-ios-dark": gmail_ios_dark,
}


def get_profile(name: str) -> Profile:
    try:
        return _PROFILE_BUILDERS[name]()
    except KeyError:
        raise KeyError(f"unknown emailsim profile {name!r} (available: {sorted(_PROFILE_BUILDERS)})") from None
