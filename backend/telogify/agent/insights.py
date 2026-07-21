"""Parse the agent's 3 insights, extract the tool-call trace, persist with source trace.

The source trace is the verbatim sequence of tool calls and their JSON returns, so every
number a published insight cites is auditable back to a logged tool return.
"""

import json

from sqlmodel import Session as DBSession
from sqlmodel import delete

from telogify.agent.guardrails import flag_unsupported_claims
from telogify.models import Insight
from telogify.serialize import round_prose_numbers, strip_em_dashes

_REQUIRED_KEYS = ("team", "header", "explanation_web", "explanation_email")
_QUALI_REQUIRED_KEYS = ("team", "header", "explanation_web", "explanation_email")


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    # Anthropic content can be a list of blocks; join text parts.
    if isinstance(content, list):
        return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return str(content)


def _first_json_array(text: str) -> str | None:
    """Slice out the first balanced [...] array, ignoring brackets inside strings. Tolerates
    trailing prose the agent sometimes appends (which broke a naive find('[')..rfind(']')
    slice: a trailing 'note [x]' made json.loads choke on 'Extra data')."""
    start = text.find("[")
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            esc = c == "\\" and not esc
            if c == '"' and not esc:
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def parse_insights(
    final_text: str, count: int = 3, required_keys: tuple[str, ...] = _REQUIRED_KEYS
) -> list[dict]:
    """Parse the final message into exactly `count` insight dicts. Fails loud on bad output."""
    array = _first_json_array(final_text)
    if array is None:
        raise ValueError("Agent final message contained no JSON array of insights.")
    data = json.loads(array)
    if not isinstance(data, list) or len(data) < count:
        raise ValueError(f"Expected {count} insights, got {len(data) if isinstance(data, list) else '?'}.")
    insights = data[:count]
    for ins in insights:
        missing = [k for k in required_keys if k not in ins]
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
    weekend_id: int,
    insights: list[dict],
    trace: list[dict],
    db: DBSession,
    *,
    model: type = Insight,
    count: int = 3,
    model_used: str | None = None,
    prompt_version: str | None = None,
) -> list:
    """Write the `count` insights (slots 1..count), em-dash-stripped, each carrying the full
    trace. `model` is any SQLModel table shaped like Insight (weekend_id, slot, header,
    explanation_web, explanation_email, source_tool_calls_json); a `team` key in an insight
    dict is only set on the row if the model has a `team` column (QualiInsight does).
    `model_used`/`prompt_version` stamp which LLM and which prompt revision produced this
    batch, for audit (see agent/prompts.PROMPT_VERSION)."""
    db.exec(delete(model).where(model.weekend_id == weekend_id))
    rows = []
    for slot, ins in enumerate(insights[:count], start=1):
        header = round_prose_numbers(strip_em_dashes(ins["header"]))
        web = round_prose_numbers(strip_em_dashes(ins["explanation_web"]))
        email = round_prose_numbers(strip_em_dashes(ins["explanation_email"]))

        # Regression net: warn loudly if the prose contains a claim the data cannot support.
        flagged = flag_unsupported_claims(f"{header} {web} {email}")
        if flagged:
            print(f"[guardrail] insight {slot} contains unsupported claim phrases: {flagged}")

        extra = {"team": ins["team"]} if "team" in ins and hasattr(model, "team") else {}
        row = model(
            weekend_id=weekend_id,
            slot=slot,
            header=header,
            explanation_web=web,
            explanation_email=email,
            source_tool_calls_json=trace,
            model_used=model_used,
            prompt_version=prompt_version,
            **extra,
        )
        db.add(row)
        rows.append(row)
    db.commit()
    return rows
