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
    # setup inferred from telemetry we never see (no wing level, no Saturday->Sunday car swap);
    # a single noisy speed segment must not become a "two different cars" story
    "wing swap",
    "wing-level swap",
    "wing level swap",
    "wing change",
    "changed its wing",
    "two completely different cars",
    "two different cars",
    "completely different car across",
    # retirement CAUSE we never ingest: we know a car retired, never why. Do not invent one.
    # (a "collision" IS allowed now: it comes from ingested race control events, not the agent.)
    "crash",
    "hit the wall",
    "into the wall",
    "spun off",
    "spun out",
    "mechanical failure",
    "mechanical issue",
    "mechanical problem",
    "engine failure",
    "engine blew",
    "power unit failure",
    "brake failure",
    "brakes failed",
    "brakes on fire",
    "caught fire",
    "caught on fire",
    "went up in smoke",
    "blew up",
    "gearbox",
    "hydraulic",
    "suspension failure",
    "suspension damage",
    "puncture",
    "retired with",
    "retired due to",
    "retired because",
    # causal retirement narratives tied to steward-noted incidents (see validation.py too)
    "retirement traces",
]

_NUMBER_WORD = (
    r"\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
    r"fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty"
)

# Regex patterns for retirement-lap counts phrased with a number the blocklist substrings
# above can't catch literally (e.g. "retired on lap 37", "out after just five laps").
# "on lap N" for race-control events (collision, penalty, etc.) is allowed; see
# _flag_on_lap_phrases.
_REGEX_BLOCKLIST = [
    re.compile(rf"\bafter (?:just )?(?:{_NUMBER_WORD}) laps?\b"),
    re.compile(r"\bcompleted \d+ laps\b"),
    re.compile(r"\bretired after \d+\b"),
    re.compile(r"\bpole to flag in the sprint\b"),
    re.compile(r"\bled from pole in the sprint\b"),
    # implausible single-corner / single-straight speed gap (>=31 km/h), above the miner caps;
    # matches "67.5 km/h (42 mph) slower", "99 km/h more", "41 km/h ... gap", not absolute
    # top speeds ("331 km/h on the straights") or small legit gaps ("12 km/h slower").
    re.compile(
        r"\b(?:3[1-9]|[4-9]\d|\d{3})(?:\.\d+)? km/h(?: \([^)]*\))? "
        r"(?:slower|faster|quicker|shy|off|behind|adrift|deficit)\b"
    ),
    # DRS state is not reliably known (FastF1: channel semantics "need more research"), so any
    # DRS mention is unsupported. Straights are described plainly, never as "DRS zones".
    re.compile(r"\bdrs\b", re.IGNORECASE),
    # a word repeated possessively ("Alpine's Alpine", "Ferrari's Ferrari") - the car-centric
    # voice occasionally doubles a constructor name; a prompt note did not reliably stop it.
    re.compile(r"\b(\w+)'s \1\b", re.IGNORECASE),
    # retirement causally linked to a lap-N incident without collision/retirement RC kind
    re.compile(
        r"\b(?:retired|retirement|did not finish)\b[^.]{0,120}\b(?:traces to|due to|because of|"
        r"caused by|following)\b[^.]{0,80}\bincident\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bafter (?:an |a )?incident\b[^.]{0,60}\b(?:retired|retirement)\b", re.IGNORECASE),
    re.compile(r"\b(?:retired|retirement)\b[^.]{0,60}\bafter (?:an |a )?incident\b", re.IGNORECASE),
]

_RC_LAP_CONTEXT = re.compile(
    r"\b(?:collision|incident|penalty|penalties|safety car|virtual safety car|"
    r"caution|forced off|forced-off|red flag|double yellow|deployed|noted|investigation)\b"
)
_RETIREMENT_LAP_CONTEXT = re.compile(
    r"\b(?:retired|retirement|ended in retirement|before retiring|was out|went out|"
    r"pulled off|did not finish|dnf)\b"
)
_OVERTAKE_LAP_CONTEXT = re.compile(
    r"\b(?:passed|overtook|got past|took the lead|leading on|made up places)\b"
)
_ON_LAP = re.compile(r"\bon lap \d+\b")

# Actionable rewrite hints keyed by flagged phrase (substring blocklist entries only).
_FIX_HINTS: dict[str, str] = {
    "front row": 'Say the actual grid position ("started second", "qualified third"). Never "front row".',
    "front-row": 'Say the actual grid position ("started second", "qualified third"). Never "front row".',
    "row two": 'Say the actual grid position ("started third", "qualified fourth"). Never "row two".',
    "second row": 'Say the actual grid position ("started third", "qualified fourth"). Never "second row".',
    "third row": 'Say the actual grid position ("started fifth", "qualified sixth"). Never "third row".',
    "maiden": "Do not use career or season framing. State only this weekend's finishing position.",
    "debut": "Do not use career or season framing. State only this weekend's finishing position.",
    "this season": "Do not reference the season or standings. State only this weekend's result.",
    "pole to flag": "You do not know who led during the race. State grid and finish only.",
    "clean sweep": "Do not claim a driver won the weekend. State separate session results.",
    "won the weekend": "Do not claim a driver won the weekend. State separate session results.",
    "double win": "Do not claim a double win. State the sprint and race finishing positions separately.",
    "won both": "Do not claim a double win. State the sprint and race finishing positions separately.",
    "drs": "Do not mention DRS. Describe straights plainly.",
    "retirement traces": (
        "Do not link a retirement to a steward-noted incident. State retired/DNF and cite "
        "incidents separately without causation unless race control shows a collision or retirement."
    ),
}

_VALIDATION_FIX_HINTS: tuple[tuple[str, str], ...] = (
    (
        "retirement causally linked",
        "Do not attribute a retirement to a steward-noted incident. State retired/DNF; cite RC separately.",
    ),
    (
        "practice sector_delta",
        "Sector deficits from practice candidates cannot be cited as qualifying weaknesses.",
    ),
    (
        "lowest-clip/deployment claim",
        "Re-check get_deployment: another car has lower total_clip_m than the value you cited.",
    ),
    (
        "shortest-clip claim",
        "Re-check get_deployment: another car has lower max_clip_m than the value you cited.",
    ),
    (
        "untraceable recap",
        "Only cite retirement cause, mechanical failure, or retirement lap from get_weekend_recap facts.",
    ),
)


def _flag_on_lap_phrases(low: str) -> list[str]:
    """Block retirement-lap and overtake-lap claims; allow race-control lap cites."""
    flagged: list[str] = []
    for match in _ON_LAP.finditer(low):
        start, end = match.start(), match.end()
        ctx = low[max(0, start - 60) : min(len(low), end + 60)]
        if _RC_LAP_CONTEXT.search(ctx):
            continue
        if _RETIREMENT_LAP_CONTEXT.search(ctx) or _OVERTAKE_LAP_CONTEXT.search(ctx):
            flagged.append(match.group(0))
    return flagged


def fix_hints_for_phrases(phrases: list[str]) -> list[str]:
    """Return deduplicated rewrite instructions for flagged blocklist phrases."""
    seen: set[str] = set()
    hints: list[str] = []
    for phrase in phrases:
        key = phrase.lower()
        hint = _FIX_HINTS.get(key)
        if hint is None:
            for prefix, validation_hint in _VALIDATION_FIX_HINTS:
                if prefix in key:
                    hint = validation_hint
                    break
        if hint is None:
            continue
        if hint in seen:
            continue
        seen.add(hint)
        hints.append(hint)
    return hints


def format_insight_validation_feedback(flagged: dict[int, list[str]]) -> str:
    """Build retry text for the insight agent after guardrail or validation failure."""
    all_phrases = [p for issues in flagged.values() for p in issues]
    hints = fix_hints_for_phrases(all_phrases)
    lines = [
        "Your last set of 3 insights failed validation. Specifically, insight "
        f"slot(s) {sorted(flagged)} had issues: {flagged}.",
    ]
    if hints:
        lines.append("Fix these before rewriting:")
        lines.extend(f"- {h}" for h in hints)
    lines.append(
        "Rewrite ALL 3 insights from scratch, fixing every issue while keeping every "
        "number grounded in tool returns. Check header, explanation_web, AND "
        "explanation_email: a banned phrase in any field fails the slot. Output the "
        "JSON array as your final message; do not wrap it in Markdown backticks."
    )
    return " ".join(lines)


def flag_unsupported_claims(text: str | None) -> list[str]:
    """Return the blocklisted phrases present in `text` (case-insensitive)."""
    if not text:
        return []
    low = text.lower()
    flagged = [phrase for phrase in _BLOCKLIST if phrase in low]
    flagged += [m.group(0) for pattern in _REGEX_BLOCKLIST for m in pattern.finditer(low)]
    flagged += _flag_on_lap_phrases(low)
    return flagged
