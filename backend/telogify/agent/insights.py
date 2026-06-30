"""Parse the agent's 3 insights, extract the tool-call trace, persist with source trace.

The source trace is the verbatim sequence of tool calls and their JSON returns, so every
number a published insight cites is auditable back to a logged tool return.
"""

import json

from sqlmodel import Session as DBSession
from sqlmodel import delete

from telogify.models import Insight
from telogify.serialize import strip_em_dashes

_REQUIRED_KEYS = ("header", "explanation_web", "explanation_email")


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    # Anthropic content can be a list of blocks; join text parts.
    if isinstance(content, list):
        return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return str(content)


def parse_insights(final_text: str) -> list[dict]:
    """Parse the final message into exactly 3 insight dicts. Fails loud on bad output."""
    start, end = final_text.find("["), final_text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("Agent final message contained no JSON array of insights.")
    data = json.loads(final_text[start : end + 1])
    if not isinstance(data, list) or len(data) < 3:
        raise ValueError(f"Expected 3 insights, got {len(data) if isinstance(data, list) else '?'}.")
    insights = data[:3]
    for ins in insights:
        missing = [k for k in _REQUIRED_KEYS if k not in ins]
        if missing:
            raise ValueError(f"Insight missing keys: {missing}")
    return insights


def extract_trace(messages: list) -> list[dict]:
    """Pair every tool call with its return, in order: [{tool, args, result}]."""
    results: dict[str, str] = {}
    for m in messages:
        if getattr(m, "type", None) == "tool":
            results[m.tool_call_id] = _content_text(m.content)
    trace: list[dict] = []
    for m in messages:
        for call in getattr(m, "tool_calls", None) or []:
            trace.append(
                {
                    "tool": call["name"],
                    "args": call.get("args", {}),
                    "result": results.get(call.get("id")),
                }
            )
    return trace


def persist_insights(
    weekend_id: int, insights: list[dict], trace: list[dict], db: DBSession
) -> list[Insight]:
    """Write the 3 insights (slots 1-3), em-dash-stripped, each carrying the full trace."""
    db.exec(delete(Insight).where(Insight.weekend_id == weekend_id))
    rows = []
    for slot, ins in enumerate(insights[:3], start=1):
        row = Insight(
            weekend_id=weekend_id,
            slot=slot,
            header=strip_em_dashes(ins["header"]),
            explanation_web=strip_em_dashes(ins["explanation_web"]),
            explanation_email=strip_em_dashes(ins["explanation_email"]),
            source_tool_calls_json=trace,
        )
        db.add(row)
        rows.append(row)
    db.commit()
    return rows
