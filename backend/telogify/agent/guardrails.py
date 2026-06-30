"""Regression net for insight prose. Flags phrases the single-weekend data can never
support: first-time/season framing, lap-by-lap leadership, and start-lap events. The prompt
is the primary defense; this catches anything that slips through so the user is alerted."""

# High-precision substrings (case-insensitive). Each is a claim the agent has no data for.
_BLOCKLIST = [
    # first-time / season / career framing
    "maiden",
    "first win",
    "first victory",
    "first grand prix",
    "first career",
    "back-to-back",
    "back to back",
    "consecutive win",
    "this season",
    "championship",
    "debut",
    "first race",
    "first weekend",
    "newcomer",
    # running order / leadership not in the data
    "pole to flag",
    "wire to wire",
    "lights to flag",
    "led every lap",
    "led throughout",
    "led from the front",
    "controlled from the front",
    "dominated from the front",
    "led from start to finish",
    # start / first-lap events
    "off the line",
    "first corner",
    "turn one",
    "got the jump",
]


def flag_unsupported_claims(text: str | None) -> list[str]:
    """Return the blocklisted phrases present in `text` (case-insensitive)."""
    if not text:
        return []
    low = text.lower()
    return [phrase for phrase in _BLOCKLIST if phrase in low]
