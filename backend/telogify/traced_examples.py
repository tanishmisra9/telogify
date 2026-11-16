"""Real, traceable examples for the How-it-works page: one number from a published insight, and the exact row of
the logged tool return it came from. Pure (no DB): the route feeds it each weekend's insights and trace.

Nothing here invents a figure. A prose number is only offered when it matches EXACTLY ONE numeric leaf across the
batch's tool returns (rounded to the number of decimals the prose shows), so the excerpt is unambiguous. An insight
with no such number is skipped. Reads `validation._QUANTITY_RE` (the prose-quantity pattern the hard gate uses)
without changing it."""

import json
import re
from typing import Any

from telogify.agent.validation import _QUANTITY_RE

MAX_ROW_FIELDS = 8
# A candidate-ranking return holds magnitudes, not facts about the weekend: a prose number that happens to equal one
# is a coincidence, not its source.
_SKIP_TOOLS = {"get_candidate_insights"}


def parse_trace(trace: list[dict]) -> list[dict]:
    """Decode each tool return once: [{tool, args, data}]. A return that isn't JSON is dropped."""
    out = []
    for call in trace or []:
        if call.get("tool") in _SKIP_TOOLS or not isinstance(call.get("result"), str):
            continue
        try:
            out.append({"tool": call["tool"], "args": call.get("args", {}), "data": json.loads(call["result"])})
        except (ValueError, KeyError):
            continue
    return out


def _leaves(node: Any, parent: dict | None = None, key: str | None = None):
    """Every numeric leaf as (parent dict, key, value); only leaves whose parent is an object (a row)."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _leaves(v, node, k)
    elif isinstance(node, list):
        for v in node:
            yield from _leaves(v, None, None)
    elif parent is not None and isinstance(node, (int, float)) and not isinstance(node, bool):
        yield parent, key, node


# The prose unit and the field names that can carry it. A leaf whose key says a DIFFERENT quantity ("0.25 seconds"
# against a percentage field that also reads 0.25) is not a source, however unique the value. A unit with no entry
# here (or a key that names no unit) is left to the value match alone.
_UNIT_KEYS = (
    (re.compile(r"km/h|kph|\bkm\b", re.I), re.compile(r"kmh|km_h|speed", re.I)),
    (re.compile(r"mph", re.I), re.compile(r"mph", re.I)),
    (re.compile(r"%"), re.compile(r"pct|percent", re.I)),
    (re.compile(r"m/s", re.I), re.compile(r"ms2|accel", re.I)),
    (re.compile(r"metre|meter", re.I), re.compile(r"(^|_)m($|_)|metre|dist", re.I)),
    (re.compile(r"sec|\bs\b", re.I), re.compile(r"(^|_)s($|_)|sec", re.I)),
)


def _key_fits_unit(key: str, prose_unit: str) -> bool:
    for unit_re, key_re in _UNIT_KEYS:
        if unit_re.search(prose_unit):
            return bool(key_re.search(key))
    return True


def _decimals(text: str) -> int:
    return len(text.split(".")[1]) if "." in text else 0


def _matches(parsed: list[dict], text: str, prose_unit: str) -> list[tuple[dict, dict, str, float]]:
    """(call, row, key, value) for every leaf whose value rounds to the prose number `text` and whose key fits its unit."""
    nd, qty = _decimals(text), float(text)
    return [
        (call, row, key, val)
        for call in parsed
        for row, key, val in _leaves(call["data"])
        if round(val, nd) == qty and _key_fits_unit(key, prose_unit)
    ]


def _excerpt(row: dict, key: str) -> dict:
    """The row's scalar fields, capped, always including the matched key."""
    scalars = {k: v for k, v in row.items() if isinstance(v, (str, int, float, bool)) or v is None}
    keep = [k for k in scalars if k != key][: MAX_ROW_FIELDS - 1]
    return {k: scalars[k] for k in scalars if k in keep or k == key}


def example_for(insight: dict, parsed: list[dict]) -> dict | None:
    """The first prose figure of `insight` with exactly one source leaf, or None."""
    for m in _QUANTITY_RE.finditer(insight["explanation_web"]):
        text = m.group(1) or m.group(2)
        # A whole-number figure ("3 seconds") can coincide with an unrelated integer leaf (a stint or lap number) and
        # still be a "unique" hit, so only figures with decimals are traceable by value alone.
        if text is None or "." not in text:
            continue
        hits = _matches(parsed, text, m.group(0)[len(text):] if m.group(1) else "mph")
        if len(hits) != 1:
            continue
        call, row, key, val = hits[0]
        return {
            "year": insight["year"],
            "round": insight["round"],
            "event_name": insight["event_name"],
            "header": insight["header"],
            "explanation_web": insight["explanation_web"],
            "traced": text,
            "traced_with_unit": m.group(0).strip(),
            "raw": repr(val),
            "key": key,
            "tool": call["tool"],
            "args": call["args"],
            "row": _excerpt(row, key),
        }
    return None
