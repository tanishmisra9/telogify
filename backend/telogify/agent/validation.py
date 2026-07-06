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
    for conflict in flag_cross_insight_conflicts(insights):
        # Attach cross-insight conflicts to every slot mentioned in the message.
        for slot in re.findall(r"\d+", conflict.split(" contradict")[0]):
            flagged.setdefault(int(slot), []).append(conflict)
    return flagged
