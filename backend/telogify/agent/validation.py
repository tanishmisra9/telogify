"""Post-generation validation for insight prose.

Pure functions: check that cited quantities appear in the tool trace and that
cross-insight speed/pace claims do not contradict without session qualification.
"""

import json
import math
import re

# Constructors the agent may name in prose (longest first for substring matching).
_CONSTRUCTORS = (
    "Red Bull Racing",
    "Racing Bulls",
    "Aston Martin",
    "Mercedes",
    "McLaren",
    "Ferrari",
    "Williams",
    "Alpine",
    "Cadillac",
    "Haas",
)

_SLOW_SPEED = (
    "slowest",
    "lowest top speed",
    "third-slowest",
    "fourth-slowest",
    "fifth-slowest",
    "weak straight-line",
    "slow straight-line",
    "lacked straight-line",
    "straight-line deficit",
)

_FAST_SPEED = (
    "fastest",
    "highest top speed",
    "strong straight-line",
    "quick straight-line",
    "strongest straight-line",
    "straight-line advantage",
)

# Numbers tied to a unit or parenthetical mph (skip bare ordinals like "21st").
_SECTOR_DEFICIT = re.compile(
    r"(\d+(?:\.\d+)?)\s*seconds?\s+(?:slow|off|behind|deficit)",
    re.IGNORECASE,
)

_RETIREMENT_CAUSE_RC_KINDS = frozenset({"collision", "retirement", "forced_off"})

_CAUSAL_RETIREMENT = re.compile(
    r"\b(?:traces to|traced to|due to the|because of the|caused by the|following the|"
    r"after (?:an |a )?incident)\b",
    re.IGNORECASE,
)

_SUPERLATIVE_FIELD = re.compile(
    r"\b(?:lowest|smallest|cleanest|fewest|minimum)\b[^.]{0,100}\b(?:in|of)\s+(?:the\s+)?(?:field|grid)\b",
    re.IGNORECASE,
)

_CLIP_SUPERLATIVE = re.compile(
    r"\b(?:lowest|smallest|cleanest|fewest|shortest)\b[^.]{0,80}\b(?:clip|deployment|ers)\b",
    re.IGNORECASE,
)

_CLIP_METRES = re.compile(r"\b(\d+(?:\.\d+)?)\s*(?:m|metres?|meters?)\b", re.IGNORECASE)

_SESSION_ABBREV = re.compile(r"\b(?:\bin\s+)?(?:SQ|Q)\b|\bin\s+R\b|\bSPRINT\b", re.IGNORECASE)

_QUALIFYING_CTX = re.compile(
    r"\bqualifying\b|\bin q\b|q-lap|speed trap",
    re.IGNORECASE,
)

_SECTOR_CTX = re.compile(
    r"\bsector[- ]?\d|middle sector",
    re.IGNORECASE,
)

_RECAP_MECHANICAL = (
    "mechanical failure",
    "mechanical issue",
    "mechanical problem",
    "engine failure",
    "engine blew",
    "power unit failure",
    "brake failure",
    "brakes failed",
    "coolant",
    "gearbox",
    "hydraulic",
    "suspension failure",
    "retired with",
    "retired due to",
    "retired because",
)

_ON_LAP_PHRASE = re.compile(r"\bon lap (\d+)\b", re.IGNORECASE)


def _parse_tool_results(trace: list[dict], tool_name: str) -> list:
    rows: list = []
    for entry in trace:
        if entry.get("tool") != tool_name:
            continue
        result = entry.get("result")
        if not result:
            continue
        try:
            data = json.loads(result) if isinstance(result, str) else result
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, list):
            rows.extend(data)
        elif isinstance(data, dict):
            rows.append(data)
    return rows


def _rc_events(trace: list[dict]) -> list[dict]:
    return _parse_tool_results(trace, "get_race_control_events")


def _deployments(trace: list[dict]) -> list[dict]:
    return [row for row in _parse_tool_results(trace, "get_deployment") if "total_clip_m" in row]


def _practice_sector_deficits(trace: list[dict]) -> set[float]:
    deficits: set[float] = set()
    for cand in _parse_tool_results(trace, "get_candidate_insights"):
        refs = cand.get("source_refs") or []
        if isinstance(refs, str):
            try:
                refs = json.loads(refs)
            except json.JSONDecodeError:
                continue
        if not isinstance(refs, list):
            continue
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            if ref.get("type") == "sector_delta" and "deficit_s" in ref:
                deficits.add(round(float(ref["deficit_s"]), 3))
    return deficits


def flag_false_retirement_causation(text: str, trace: list[dict]) -> list[str]:
    """Block linking a retirement/DNF to steward-noted incidents when RC has no real cause."""
    low = text.lower()
    retirement = bool(
        re.search(r"\b(?:retired|retirement|did not finish|\bdnf\b)\b", low) or "retirement traces" in low
    )
    if not retirement:
        return []
    if not (_CAUSAL_RETIREMENT.search(low) or "retirement traces" in low):
        return []
    events = _rc_events(trace)
    if not events:
        return []
    kinds = {e.get("kind") for e in events if e.get("kind")}
    if kinds & _RETIREMENT_CAUSE_RC_KINDS:
        return []
    if kinds <= {"incident", "penalty", "safety_car"} and (
        "incident" in kinds or re.search(r"\bincident\b", low)
    ):
        return [
            "retirement causally linked to race control but events are steward-noted incidents only"
        ]
    return []


def flag_qualifying_practice_sector_mismatch(text: str, trace: list[dict]) -> list[str]:
    """Block citing a practice sector_delta deficit while framing it as a qualifying weakness."""
    practice_deficits = _practice_sector_deficits(trace)
    if not practice_deficits:
        return []
    for match in _SECTOR_DEFICIT.finditer(text):
        deficit = float(match.group(1))
        window = text[max(0, match.start() - 150) : min(len(text), match.end() + 150)]
        low_window = window.lower()
        if not _QUALIFYING_CTX.search(low_window):
            continue
        if re.search(r"\bpractice\b|\bfp[123]\b", low_window):
            continue
        if not _SECTOR_CTX.search(low_window):
            continue
        if not any(math.isclose(deficit, d, abs_tol=0.001) for d in practice_deficits):
            continue
        return [
            "sector deficit cited in qualifying context but matching value is practice sector_delta only"
        ]
    return []


def flag_false_deployment_superlative(text: str, trace: list[dict]) -> list[str]:
    """Block lowest/shortest clip claims when deployment trace shows a lower value."""
    low = text.lower()
    claims_total_min = bool(_SUPERLATIVE_FIELD.search(text)) or bool(_CLIP_SUPERLATIVE.search(low))
    claims_shortest = bool(re.search(r"\bshortest\b[^.]{0,80}\bclip\b", low))
    if not claims_total_min and not claims_shortest:
        return []
    deployments = _deployments(trace)
    if len(deployments) < 2:
        return []
    min_total = min(float(d["total_clip_m"]) for d in deployments)
    min_max_clip = min(float(d["max_clip_m"]) for d in deployments)
    for match in _CLIP_METRES.finditer(text):
        cited = float(match.group(1))
        if cited < 50:
            continue
        if claims_shortest and cited > min_max_clip + 0.5:
            return [
                f"shortest-clip claim ({cited}m) but field minimum max_clip_m is {min_max_clip}m in tool trace"
            ]
        if claims_total_min and cited > min_total + 0.5:
            return [
                f"lowest-clip/deployment claim ({cited}m) but field minimum total_clip_m is {min_total}m in tool trace"
            ]
    return []


def _recap_facts(trace: list[dict]) -> list[dict]:
    for entry in trace:
        if entry.get("tool") != "get_weekend_recap":
            continue
        result = entry.get("result")
        if not result:
            continue
        try:
            data = json.loads(result) if isinstance(result, str) else result
        except (json.JSONDecodeError, TypeError):
            continue
        sessions = data.get("sessions") or {}
        facts: list[dict] = []
        for session_data in sessions.values():
            if not isinstance(session_data, dict) or not session_data.get("present"):
                continue
            for fact in session_data.get("facts") or []:
                if isinstance(fact, dict):
                    facts.append(fact)
        return facts
    return []


def _recap_blob(facts: list[dict]) -> str:
    parts: list[str] = []
    for fact in facts:
        parts.append(fact.get("text", ""))
        if fact.get("lap") is not None:
            parts.append(str(fact["lap"]))
    return " ".join(parts).lower()


def filter_guardrails_with_recap(phrases: list[str], text: str, trace: list[dict]) -> list[str]:
    """Drop guardrail hits allowed when get_weekend_recap supports the claim."""
    facts = _recap_facts(trace)
    if not facts:
        return phrases
    blob = _recap_blob(facts)
    laps = {int(f["lap"]) for f in facts if f.get("lap") is not None}
    has_retirement = any(f.get("kind") == "retirement" for f in facts)
    low_text = text.lower()
    kept: list[str] = []
    for phrase in phrases:
        low = phrase.lower()
        if low in blob:
            continue
        lap_match = _ON_LAP_PHRASE.match(low)
        if lap_match:
            lap = int(lap_match.group(1))
            if lap in laps and re.search(r"\b(?:retired|retirement|dnf|did not finish)\b", low_text):
                continue
        if low in ("retired due to", "retired because", "retired with") and has_retirement:
            continue
        if any(term in low for term in _RECAP_MECHANICAL) and any(term in blob for term in _RECAP_MECHANICAL if term in low):
            continue
        if any(term in low and term in blob for term in _RECAP_MECHANICAL):
            continue
        kept.append(phrase)
    return kept


def _recap_tool_called(trace: list[dict]) -> bool:
    return any(entry.get("tool") == "get_weekend_recap" for entry in trace)


def flag_untraceable_recap_claims(text: str, trace: list[dict]) -> list[str]:
    """Flag mechanical/retirement-lap claims not present in get_weekend_recap."""
    if not _recap_tool_called(trace):
        return []
    facts = _recap_facts(trace)
    blob = _recap_blob(facts)
    laps = {int(f["lap"]) for f in facts if f.get("lap") is not None}
    low = text.lower()
    issues: list[str] = []

    for term in _RECAP_MECHANICAL:
        if term in low and term not in blob:
            issues.append(f"untraceable recap: mechanical phrase '{term}' not in get_weekend_recap")
            break

    for match in _ON_LAP_PHRASE.finditer(low):
        lap = int(match.group(1))
        window = low[max(0, match.start() - 80) : match.end() + 80]
        if re.search(r"\b(?:retired|retirement|dnf|did not finish)\b", window) and lap not in laps:
            issues.append(f"untraceable recap: retirement lap {lap} not in get_weekend_recap")
            break

    return issues


_QUANTITY_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:km/h|kph|seconds|second|\bsec\b|\bs\b|%)"
    r"|(?:\(\s*(\d+(?:\.\d+)?)\s*mph\s*\))",
    re.IGNORECASE,
)


def _insight_text(ins: dict) -> str:
    return f"{ins.get('header', '')} {ins.get('explanation_web', '')} {ins.get('explanation_email', '')}"


def _trace_blob(trace: list[dict]) -> str:
    parts: list[str] = []
    for entry in trace:
        result = entry.get("result")
        if result is None:
            continue
        if isinstance(result, str):
            parts.append(result)
        else:
            parts.append(json.dumps(result))
    return " ".join(parts)


_TRACE_FLOAT_RE = re.compile(r"[-+]?(?:\d+\.\d+|\d+)(?:[eE][-+]?\d+)?")


def _number_variants(value: float) -> set[str]:
    out = {str(value), f"{value:.1f}", f"{value:.2f}", f"{value:.3f}"}
    rounded = round(value, 1)
    out.add(str(rounded))
    if value == int(value):
        out.add(str(int(value)))
    return out


def _trace_floats(blob: str) -> list[float]:
    values: list[float] = []
    for match in _TRACE_FLOAT_RE.finditer(blob):
        try:
            values.append(float(match.group(0)))
        except ValueError:
            continue
    return values


def _number_traced(qty: float, blob: str, trace_values: list[float]) -> bool:
    if any(v in blob for v in _number_variants(qty)):
        return True
    return any(math.isclose(qty, tv, rel_tol=1e-4, abs_tol=0.001) for tv in trace_values)


def extract_prose_quantities(text: str) -> list[float]:
    """Pull telemetry-style numbers from insight prose (speeds, gaps, percentages)."""
    found: list[float] = []
    for m in _QUANTITY_RE.finditer(text):
        raw = m.group(1) or m.group(2)
        if raw is not None:
            found.append(float(raw))
    return found


def flag_unquantified_recap_cause(text: str, trace: list[dict]) -> list[str]:
    """Flag a recap fact used as a standalone narrative with no quantified number attached.

    Recap may only appear as the stated cause of a pace/telemetry figure already in the same
    insight; a mechanical/damage/retirement phrase with no quantity nearby is journalism, not
    an insight, and must be rejected.
    """
    if not _recap_tool_called(trace):
        return []
    facts = _recap_facts(trace)
    if not facts:
        return []
    blob = _recap_blob(facts)
    low = text.lower()
    mentions_recap = any(term in low and term in blob for term in _RECAP_MECHANICAL) or any(
        (f.get("text") or "").lower() in low for f in facts if f.get("text")
    )
    if not mentions_recap:
        return []
    if _QUANTITY_RE.search(text):
        return []
    return ["unquantified recap: cites a recap event with no quantified pace/telemetry number attached"]


def flag_weak_deployment_cluster(text: str, trace: list[dict]) -> list[str]:
    """Retry when deployment insight cites multiple leaders with clustered clip distances."""
    del trace  # clip distances are validated from prose only
    if not re.search(r"\bclip\b|deployment|braking zone", text, re.IGNORECASE):
        return []
    clips = [float(m.group(1)) for m in _CLIP_METRES.finditer(text)]
    if len(clips) < 2:
        return []
    if max(clips) - min(clips) > 100:
        return []
    return [
        "weak deployment: cited qualifiers clip within about 100 metres; choose a stronger finding"
    ]


def flag_session_abbreviations(text: str) -> list[str]:
    """Retry when insight prose uses Q/SQ/R/SPRINT instead of plain session names."""
    if _SESSION_ABBREV.search(text):
        return ["language: use qualifying, sprint qualifying, the race, or the sprint; not Q/SQ/R/SPRINT"]
    return []


def flag_untraceable_numbers(text: str, trace: list[dict]) -> list[str]:
    """Return quantity strings cited in prose that do not appear in any tool return."""
    if not trace:
        return []
    blob = _trace_blob(trace)
    trace_values = _trace_floats(blob)
    untraceable: list[str] = []
    for qty in extract_prose_quantities(text):
        if not _number_traced(qty, blob, trace_values):
            untraceable.append(str(qty))
    return untraceable


def _speed_polarity(text: str, team: str) -> str | None:
    low = text.lower()
    if team.lower() not in low:
        return None
    if any(m in low for m in _SLOW_SPEED):
        return "slow"
    if any(m in low for m in _FAST_SPEED):
        return "fast"
    return None


def _session_tags(text: str) -> set[str]:
    low = text.lower()
    tags: set[str] = set()
    if "qualifying" in low or " in q" in low or low.startswith("q "):
        tags.add("qualifying")
    if "sprint" in low:
        tags.add("sprint")
    if " race" in low or "in the race" in low or low.endswith(" race"):
        tags.add("race")
    return tags


def flag_cross_insight_conflicts(insights: list[dict]) -> list[str]:
    """Flag opposing straight-line/speed characterizations for the same constructor."""
    conflicts: list[str] = []
    for team in _CONSTRUCTORS:
        readings: list[tuple[int, str, set[str]]] = []
        for i, ins in enumerate(insights, start=1):
            text = _insight_text(ins)
            polarity = _speed_polarity(text, team)
            if polarity:
                readings.append((i, polarity, _session_tags(text)))
        slow = [(s, tags) for s, p, tags in readings if p == "slow"]
        fast = [(s, tags) for s, p, tags in readings if p == "fast"]
        if not slow or not fast:
            continue
        # Allow conflict when sessions differ (e.g. Q top speed vs R pace story).
        reconciled = False
        for _, slow_tags in slow:
            for _, fast_tags in fast:
                if slow_tags and fast_tags and slow_tags.isdisjoint(fast_tags):
                    reconciled = True
                    break
            if reconciled:
                break
        if reconciled:
            continue
        slow_slots = sorted(s for s, _ in slow)
        fast_slots = sorted(s for s, _ in fast)
        conflicts.append(
            f"insights {slow_slots} and {fast_slots} contradict on {team} straight-line/speed"
        )
    return conflicts


def validate_insights(insights: list[dict], trace: list[dict]) -> dict[int, list[str]]:
    """Return per-slot validation issues (empty dict = pass). Slot keys are 1-based."""
    flagged: dict[int, list[str]] = {}
    for i, ins in enumerate(insights, start=1):
        text = _insight_text(ins)
        bad_nums = flag_untraceable_numbers(text, trace)
        if bad_nums:
            flagged.setdefault(i, []).append(f"untraceable number(s): {', '.join(bad_nums)}")
        for issue in flag_false_retirement_causation(text, trace):
            flagged.setdefault(i, []).append(issue)
        for issue in flag_qualifying_practice_sector_mismatch(text, trace):
            flagged.setdefault(i, []).append(issue)
        for issue in flag_false_deployment_superlative(text, trace):
            flagged.setdefault(i, []).append(issue)
        for issue in flag_untraceable_recap_claims(text, trace):
            flagged.setdefault(i, []).append(issue)
        for issue in flag_unquantified_recap_cause(text, trace):
            flagged.setdefault(i, []).append(issue)
        for issue in flag_weak_deployment_cluster(text, trace):
            flagged.setdefault(i, []).append(issue)
        for issue in flag_session_abbreviations(text):
            flagged.setdefault(i, []).append(issue)
    for conflict in flag_cross_insight_conflicts(insights):
        # Attach cross-insight conflicts to every slot mentioned in the message.
        for slot in re.findall(r"\d+", conflict.split(" contradict")[0]):
            flagged.setdefault(int(slot), []).append(conflict)
    return flagged
