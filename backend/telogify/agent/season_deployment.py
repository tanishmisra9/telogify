"""LLM writer for the season deployment section: one power-unit-manufacturer verdict per PU, in
rank order, from the deterministic punch/hold/fade metrics in analysis/season_deployment.py.

No tools: the metrics JSON handed to the model is the complete input, so validation traces
prose numbers straight back to that JSON instead of a tool-call trace. Same hard-gate
philosophy as agent/insights.py + pipeline._insights: nothing is persisted until a clean set
passes the jargon guardrail and number-tracing within _MAX_ATTEMPTS retries; failure raises.
"""

import json

from langchain_core.messages import HumanMessage
from sqlmodel import Session as DBSession
from sqlmodel import delete

from telogify.agent.guardrails import flag_unsupported_claims
from telogify.agent.insights import _first_json_array
from telogify.agent.llm import resolve_provider
from telogify.config import configured_llm_label
from telogify.agent.validation import _number_traced, _trace_floats, extract_prose_quantities
from telogify.analysis.season_deployment import GroupMetrics, rank_groups_best_to_worst
from telogify.models import SeasonDeploymentInsight
from telogify.serialize import round_prose_numbers, strip_em_dashes

_REQUIRED_KEYS = ("pu", "header", "explanation_web")
_MAX_ATTEMPTS = 3

# Bump on any change to SYSTEM_PROMPT below (a `git log -p -- telogify/agent/season_deployment.py`
# on this line finds the commit that changed it). Stamped onto every persisted verdict.
PROMPT_VERSION = "1.0"

SYSTEM_PROMPT = """You are Telogify's F1 analyst. You write one short verdict per power-unit \
manufacturer for the season's deployment section, for a general audience: smart fans who love \
the sport but are not engineers.

You are given a JSON array, one row per manufacturer, already ranked best to worst (rank 1 = \
strongest) by how hard its cars keep accelerating at full throttle as speed climbs through \
250-290 km/h ("punch") and past 290 km/h ("hold"); "fade" is how much acceleration a car sheds \
between those two bands. This JSON is your ONLY source of numbers: every figure you write must \
appear in it, exactly as given, never invented, rounded differently, or estimated. Do not use \
the words "punch", "hold", or "fade" in your prose; those are internal field names, not reader \
language. Instead describe plainly whether a manufacturer's cars keep accelerating hard as \
speed builds, or run out of extra shove earlier than others, always stated as a direction \
relative to the other manufacturers in the array, not as a bare number.

For each row, write ONE header (a punchy plain-English verdict) and ONE explanation_web (2 to 3 \
sentences) about that manufacturer's cars. Name which teams run that power unit using the exact \
team names given. The header and explanation_web must agree: a manufacturer ranked 1 held its \
acceleration best, never phrase that as a weakness, and a manufacturer ranked last should read \
as clearly behind the others, never dressed up as "most constant" when its numbers are simply \
weak everywhere. Cite at least one number from the row's own data. Do not compare across ranks \
using words like "second" or "third"; describe what the numbers show about that manufacturer on \
its own terms, relative to the field.

Write like a broadcaster. No engineering jargon: never "slope", "delta", "regression", \
"metric", "candidate", "signal", "sample", or units like "m/s² per km/h" (cite acceleration in \
m/s²). Never use em dashes; use commas, colons, parentheses, or restructure. Full team names, \
never abbreviations.

Output format: your final message must be a raw JSON array with exactly one object per input \
row, in the SAME order as the input. Do not wrap it in Markdown backticks or add conversational \
filler. Each object has these keys:
  "pu": the exact manufacturer name from the input row,
  "header": the punchy plain-English verdict,
  "explanation_web": the 2 to 3 sentence explanation."""


def build_metrics_payload(scatter: dict[str, list[list[float]]]) -> list[dict]:
    """Deterministic, LLM-ready metrics: one row per PU group, already ranked best to worst."""
    ranked: list[GroupMetrics] = rank_groups_best_to_worst(scatter)
    return [
        {
            "rank": i + 1,
            "pu": m.group.name,
            "works_team": m.group.works_team,
            "teams": m.teams,
            "punch_accel_ms2_250_290_kmh": m.punch,
            "hold_accel_ms2_above_290_kmh": m.hold,
            "fade_ms2": m.fade,
        }
        for i, m in enumerate(ranked)
    ]


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return str(content)


def _validate_verdicts(verdicts: list[dict], metrics: list[dict]) -> list[str]:
    """Every prose quantity must trace to the metrics JSON; jargon is blocked the same way
    as the race/quali insight prose."""
    blob = json.dumps(metrics)
    trace_values = _trace_floats(blob)
    issues: list[str] = []
    for v in verdicts:
        text = f"{v.get('header', '')} {v.get('explanation_web', '')}"
        for qty in extract_prose_quantities(text):
            if not _number_traced(qty, blob, trace_values):
                issues.append(f"untraceable number {qty} in {v.get('pu')}")
        jargon = flag_unsupported_claims(text)
        if jargon:
            issues.append(f"jargon in {v.get('pu')}: {jargon}")
    return issues


def _default_agent_runner(metrics: list[dict], feedback: str | None = None) -> str:
    provider = resolve_provider()
    model = provider.build_model()
    user_content = (
        "Here is this season's power-unit acceleration data:\n" + json.dumps(metrics, indent=2)
    )
    if feedback:
        user_content += f"\n\n{feedback}"
    messages = [provider.build_system_message(SYSTEM_PROMPT), HumanMessage(content=user_content)]
    response = model.invoke(messages)
    return _content_text(response.content)


def generate_season_deployment_verdicts(
    scatter: dict[str, list[list[float]]], *, agent_runner=None
) -> tuple[list[dict], list[dict]]:
    """Run the writer with a validate + retry loop, mirroring pipeline._insights. Returns
    (verdicts, metrics), both in rank order. Raises RuntimeError if no clean set is produced
    within _MAX_ATTEMPTS. Empty metrics (fewer than 3 PU groups with data) returns ([], [])."""
    runner = agent_runner or _default_agent_runner
    metrics = build_metrics_payload(scatter)
    if not metrics:
        return [], []

    feedback = None
    for _attempt in range(1, _MAX_ATTEMPTS + 1):
        final_text = runner(metrics, feedback)
        array = _first_json_array(final_text)
        if array is None:
            feedback = (
                "Your last message contained no JSON array. Your final message must be a raw "
                f"JSON array of exactly {len(metrics)} objects with keys {_REQUIRED_KEYS}. Do "
                "not wrap it in Markdown backticks or add conversational filler."
            )
            continue
        try:
            verdicts = json.loads(array)
        except json.JSONDecodeError as e:
            feedback = f"Your last message's JSON array did not parse ({e}). Rewrite it as valid JSON."
            continue
        if not isinstance(verdicts, list) or len(verdicts) != len(metrics):
            feedback = (
                f"Expected exactly {len(metrics)} objects, one per input row in the same "
                f"order, got {len(verdicts) if isinstance(verdicts, list) else '?'}."
            )
            continue
        missing_keys = [
            m["pu"] for m, v in zip(metrics, verdicts) if any(k not in v for k in _REQUIRED_KEYS)
        ]
        if missing_keys:
            feedback = f"These rows are missing required keys {_REQUIRED_KEYS}: {missing_keys}."
            continue

        issues = _validate_verdicts(verdicts, metrics)
        if issues:
            feedback = (
                f"Your last set of verdicts failed validation: {issues}. Rewrite ALL verdicts "
                "from scratch, keeping every number grounded in the input data and removing any "
                "jargon. Output the JSON array as your final message."
            )
            continue

        return verdicts, metrics

    raise RuntimeError(
        f"Season deployment writer failed to produce a valid, clean set within {_MAX_ATTEMPTS} attempts."
    )


def persist_season_deployment(
    year: int, verdicts: list[dict], metrics: list[dict], db: DBSession
) -> list[SeasonDeploymentInsight]:
    """Idempotent delete + reinsert for `year`, one row per PU in rank order."""
    db.exec(delete(SeasonDeploymentInsight).where(SeasonDeploymentInsight.year == year))
    rows = []
    for v, m in zip(verdicts, metrics):
        row = SeasonDeploymentInsight(
            year=year,
            rank=m["rank"],
            pu_name=m["pu"],
            works_team=m["works_team"],
            teams_json=m["teams"],
            header=round_prose_numbers(strip_em_dashes(v["header"])),
            explanation_web=round_prose_numbers(strip_em_dashes(v["explanation_web"])),
            source_metrics_json=m,
            model_used=configured_llm_label(),
            prompt_version=PROMPT_VERSION,
        )
        db.add(row)
        rows.append(row)
    db.commit()
    return rows
