"""Regression net for insight prose. Flags phrases the single-weekend data can never
support: first-time/season framing, lap-by-lap leadership, and start-lap events. This is a
hard gate, not just a warning: telogify.agent.insights and telogify.pipeline treat any
flagged phrase as a failed generation and force the agent to rewrite before anything is
persisted."""

import re

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
    # retirement lap counts (the laps field is unreliable, so never cite it)
    "completed only",
    "before retiring",
    "laps before he retired",
    "laps before she retired",
    # grouped grid labels (use plain ordinals; "front row" gets misused for P3/P4)
    "front row",
    "front-row",
    "row two",
    "second row",
    "third row",
    # sprint-weekend fabrications (no season or double-win narrative)
    "clean sweep",
    "won the weekend",
    "double win",
    "won both",
    "sprint double",
]

_NUMBER_WORD = (
    r"\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
    r"fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty"
)

# Regex patterns for retirement-lap counts phrased with a number the blocklist substrings
# above can't catch literally (e.g. "retired on lap 37", "out after just five laps").
_REGEX_BLOCKLIST = [
    re.compile(r"\bon lap \d+\b"),
    re.compile(rf"\bafter (?:just )?(?:{_NUMBER_WORD}) laps?\b"),
    re.compile(r"\bcompleted \d+ laps\b"),
    re.compile(r"\bretired after \d+\b"),
    re.compile(r"\bpole to flag in the sprint\b"),
    re.compile(r"\bled from pole in the sprint\b"),
]


def flag_unsupported_claims(text: str | None) -> list[str]:
    """Return the blocklisted phrases present in `text` (case-insensitive)."""
    if not text:
        return []
    low = text.lower()
    flagged = [phrase for phrase in _BLOCKLIST if phrase in low]
    flagged += [m.group(0) for pattern in _REGEX_BLOCKLIST for m in pattern.finditer(low)]
    return flagged
