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


def strip_em_dashes(text: str | None) -> str | None:
    if not text:
        return text
    for dash in ("—", "―", "⸺", "⸻"):  # em dash and friends
        text = text.replace(f" {dash} ", ", ").replace(dash, ", ")
    text = text.replace(" – ", " - ").replace("–", "-")  # en dash -> hyphen
    return text
