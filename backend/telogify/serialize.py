"""Text serialization helpers. The house style forbids em dashes anywhere in rendered
output, so every web/email string passes through strip_em_dashes as a safety net on top
of the system-prompt rule. Raw JSON floats copied into insight prose are rounded here
before persist."""

import re

# Five or more fractional digits is almost always a tool-return leak, not broadcast copy.
_LONG_DECIMAL = re.compile(r"\b(\d+\.\d{5,})\b")


def _rounded_number(value: float) -> str:
    av = abs(value)
    if av >= 50:
        decimals = 1
    elif av >= 1:
        decimals = 3
    else:
        decimals = 3
    out = f"{value:.{decimals}f}"
    if "." in out:
        out = out.rstrip("0").rstrip(".")
    return out


def round_prose_numbers(text: str | None) -> str | None:
    """Round over-precise decimals in insight prose (e.g. 81.98835714285714 -> 82.0)."""
    if not text:
        return text
    return _LONG_DECIMAL.sub(lambda m: _rounded_number(float(m.group(1))), text)


# A quoted time of a minute or more is a full lap, and racing quotes laps as M:SS.mmm, never as
# raw seconds. Below a minute it's a sector time or a gap, which genuinely ARE quoted in plain
# seconds, so the one-minute boundary is the real dividing line, not an arbitrary threshold.
# Checked against every persisted insight: lap times ran 66-105s while every sector time and gap
# was <=40.4s, so nothing straddles it. Bounded to 2-3 leading digits (no lap is <10s or >=1000s)
# and the \b keeps it from biting a longer number's tail.
_LAP_SECONDS = re.compile(r"\b(\d{2,3})\.(\d{1,3})\s?(?:seconds|s)\b")


def format_lap_times(text: str | None) -> str | None:
    """Rewrite whole-lap times from bare seconds into the standard racing clock
    (104.361 seconds -> 1:44.361). Sub-minute sector times and gaps are left alone."""
    if not text:
        return text

    def convert(match: re.Match) -> str:
        whole, frac = int(match.group(1)), match.group(2)
        if whole < 60:
            return match.group(0)
        return f"{whole // 60}:{whole % 60:02d}.{frac}"

    return _LAP_SECONDS.sub(convert, text)


def strip_em_dashes(text: str | None) -> str | None:
    if not text:
        return text
    for dash in ("—", "―", "⸺", "⸻"):  # em dash and friends
        text = text.replace(f" {dash} ", ", ").replace(dash, ", ")
    text = text.replace(" – ", " - ").replace("–", "-")  # en dash -> hyphen
    return text
