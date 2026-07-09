"""End-to-end weekend pipeline as a LangGraph: ingest -> analyze -> candidates -> insights.

State holds only primitives so checkpointing stays serializable; the live FastF1
WeekendData never leaves the ingest node. Each phase is idempotent (delete + reinsert),
and FastF1 caches raw data on disk, so re-running a weekend is safe and skips re-downloads.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
import json
from typing import TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from sqlmodel import Session, select

from telogify.agent.graph import build_agent
from telogify.agent.tools import _weekend_id
from telogify.agent.guardrails import flag_unsupported_claims, format_insight_validation_feedback
from telogify.agent.insights import _content_text, extract_trace, parse_insights, persist_insights
from telogify.agent.validation import filter_guardrails_with_recap, validate_insights
from telogify.analysis.attribution import store_attributions
from telogify.analysis.candidates import compute_candidates
from telogify.analysis.constructor_index import build_constructor_index
from telogify.analysis.fingerprints import store_fingerprints
from telogify.analysis.schedule import completed_rounds, fetch_season_schedule
from telogify.db import engine
from telogify.ingest.accel_samples import store_accel_samples
from telogify.ingest.loader import load_weekend
from telogify.ingest.quali_character import store_quali_character
from telogify.ingest.deployment import store_deployment
from telogify.ingest.race_control import store_race_control
from telogify.ingest.results import store_results
from telogify.ingest.sectors import store_sector_bests
from telogify.ingest.stints import store_stints
from telogify.ingest.straights import store_straights
from telogify.ingest.wikipedia import store_weekend_recap
from telogify.models import WeekendRecap


class PipelineState(TypedDict, total=False):
    year: int
    round: int
    weekend_id: int
    insight_count: int


def _ingest(state: PipelineState) -> dict:
    with Session(engine) as db:
        data = load_weekend(state["year"], state["round"], db)
        store_straights(data, db)
        store_stints(data, db)
        store_results(data, db)
        store_fingerprints(data, db)
        store_sector_bests(data, db)
        store_quali_character(data, db)
        store_race_control(data, db)
        store_deployment(data, db)
        store_accel_samples(data, db)
        store_weekend_recap(data, db)
        return {"weekend_id": data.weekend.id}


def _analyze(state: PipelineState) -> dict:
    with Session(engine) as db:
        store_attributions(state["weekend_id"], db)
        build_constructor_index(state["weekend_id"], db)
    return {}


def _candidates(state: PipelineState) -> dict:
    with Session(engine) as db:
        compute_candidates(state["weekend_id"], db)
    return {}


_MAX_INSIGHT_ATTEMPTS = 3


def _flag_all(insights: list[dict], trace: list[dict] | None = None) -> dict[int, list[str]]:
    """Flag each insight independently so feedback can name exactly which slot is bad."""
    flagged = {}
    for i, ins in enumerate(insights, start=1):
        text = f"{ins.get('header', '')} {ins.get('explanation_web', '')} {ins.get('explanation_email', '')}"
        phrases = flag_unsupported_claims(text)
        if trace:
            phrases = filter_guardrails_with_recap(phrases, text, trace)
        if phrases:
            flagged[i] = phrases
    return flagged


def _merge_flags(*maps: dict[int, list[str]]) -> dict[int, list[str]]:
    merged: dict[int, list[str]] = {}
    for m in maps:
        for slot, issues in m.items():
            merged.setdefault(slot, []).extend(issues)
    return merged


def _insights(state: PipelineState, agent_runner) -> dict:
    """Generate the 3 insights, rejecting and re-prompting on any guardrail violation.
    Nothing is persisted, and the pipeline fails loud, unless a clean set is produced within
    _MAX_INSIGHT_ATTEMPTS: shipping a fabricated claim is worse than shipping nothing."""
    feedback = None
    flagged: dict[int, list[str]] = {}
    parse_failures = 0
    last_parse_error: str | None = None
    for _attempt in range(1, _MAX_INSIGHT_ATTEMPTS + 1):
        messages = agent_runner(state["year"], state["round"], feedback=feedback)
        final = _content_text(messages[-1].content)
        try:
            insights = parse_insights(final)
        except ValueError as e:
            parse_failures += 1
            last_parse_error = str(e)
            # Malformed output (bad JSON, extra prose, wrong shape) is retryable, not fatal:
            # feed the error back and let the agent re-emit rather than crashing the run.
            feedback = (
                f"Your last message could not be parsed ({e}). Your final message must "
                "contain a raw JSON array of exactly 3 objects with keys header, "
                "explanation_web, and explanation_email. Do not wrap the array in Markdown "
                "backticks or add conversational filler."
            )
            continue
        trace = extract_trace(messages)
        flagged = _merge_flags(
            _flag_all(insights, trace),
            validate_insights(insights, trace),
        )
        if not flagged:
            trace = extract_trace(messages)
            with Session(engine) as db:
                rows = persist_insights(state["weekend_id"], insights, trace, db)
            return {"insight_count": len(rows)}
        feedback = format_insight_validation_feedback(flagged)
    if parse_failures == _MAX_INSIGHT_ATTEMPTS and not flagged:
        raise RuntimeError(
            f"Insight agent failed to produce parseable JSON after {_MAX_INSIGHT_ATTEMPTS} "
            f"attempts for {state['year']} round {state['round']}: {last_parse_error}"
        )
    raise RuntimeError(
        f"Insight agent kept producing unsupported claims after {_MAX_INSIGHT_ATTEMPTS} "
        f"attempts for {state['year']} round {state['round']}: {flagged}"
    )


def _recap_task_appendix(year: int, round: int) -> str:
    """Compact recap JSON for the agent task when Wikipedia recap is stored."""
    with Session(engine) as db:
        wid = _weekend_id(db, year, round)
        if wid is None:
            return ""
        row = db.exec(select(WeekendRecap).where(WeekendRecap.weekend_id == wid)).first()
        if row is None or not row.sessions_json:
            return ""
        sessions = {
            k: v
            for k, v in row.sessions_json.items()
            if isinstance(v, dict) and v.get("present")
        }
        if not sessions:
            return ""
        payload = {
            "source": "wikipedia",
            "page_title": row.page_title,
            "sessions": sessions,
        }
        return (
            "\n\nStored weekend recap preview (call get_weekend_recap before citing event facts):\n"
            + json.dumps(payload)
        )


def _default_agent_runner(year: int, round: int, feedback: str | None = None) -> list:
    agent = build_agent(year, round)
    task = f"Write the 3 insights for {year} round {round}."
    recap = _recap_task_appendix(year, round)
    if recap:
        task = f"{task}{recap}"
    if feedback:
        task = f"{task}\n\n{feedback}"
    result = agent.invoke(
        {"messages": [("user", task)]},
        config={"configurable": {"thread_id": f"agent-{year}-{round}"}},
    )
    return result["messages"]


def build_pipeline(agent_runner):
    g = StateGraph(PipelineState)
    g.add_node("ingest", _ingest)
    g.add_node("analyze", _analyze)
    g.add_node("candidates", _candidates)
    g.add_node("insights", lambda s: _insights(s, agent_runner))
    g.add_edge(START, "ingest")
    g.add_edge("ingest", "analyze")
    g.add_edge("analyze", "candidates")
    g.add_edge("candidates", "insights")
    g.add_edge("insights", END)
    return g.compile(checkpointer=MemorySaver())


def run_weekend(year: int, round: int, agent_runner=None) -> PipelineState:
    pipeline = build_pipeline(agent_runner or _default_agent_runner)
    return pipeline.invoke(
        {"year": year, "round": round},
        config={"configurable": {"thread_id": f"weekend-{year}-{round}"}},
    )


@dataclass
class RoundResult:
    round: int
    ok: bool
    insight_count: int = 0
    error: str | None = None


@dataclass
class SeasonRunResult:
    year: int
    rounds: list[int]
    results: list[RoundResult] = field(default_factory=list)


def season_rounds(year: int, *, now: datetime | None = None) -> list[int]:
    """Completed round numbers for a season (race session date on or before `now`)."""
    when = now or datetime.utcnow()
    return completed_rounds(fetch_season_schedule(year), when)


def run_season(
    year: int,
    agent_runner=None,
    *,
    now: datetime | None = None,
    continue_on_error: bool = True,
    on_round_start: Callable[[int, int, int], None] | None = None,
    on_round_complete: Callable[[RoundResult, int, int], None] | None = None,
) -> SeasonRunResult:
    """Run the full pipeline for every completed round in a season."""
    rounds = season_rounds(year, now=now)
    outcome = SeasonRunResult(year=year, rounds=rounds)
    total = len(rounds)
    for i, rnd in enumerate(rounds, start=1):
        if on_round_start:
            on_round_start(rnd, i, total)
        try:
            state = run_weekend(year, rnd, agent_runner=agent_runner)
            result = RoundResult(round=rnd, ok=True, insight_count=state.get("insight_count", 0))
        except Exception as exc:
            result = RoundResult(round=rnd, ok=False, error=str(exc))
        outcome.results.append(result)
        if on_round_complete:
            on_round_complete(result, i, total)
        if not result.ok and not continue_on_error:
            break
    return outcome


def run_insights_season(
    year: int,
    agent_runner=None,
    *,
    now: datetime | None = None,
    continue_on_error: bool = True,
    on_round_start: Callable[[int, int, int], None] | None = None,
    on_round_complete: Callable[[RoundResult, int, int], None] | None = None,
) -> SeasonRunResult:
    """Regenerate insights for every completed round in a season (LLM only, no FastF1 ingest)."""
    rounds = season_rounds(year, now=now)
    outcome = SeasonRunResult(year=year, rounds=rounds)
    total = len(rounds)
    for i, rnd in enumerate(rounds, start=1):
        if on_round_start:
            on_round_start(rnd, i, total)
        try:
            state = regen_insights(year, rnd, agent_runner=agent_runner)
            result = RoundResult(round=rnd, ok=True, insight_count=state.get("insight_count", 0))
        except Exception as exc:
            result = RoundResult(round=rnd, ok=False, error=str(exc))
        outcome.results.append(result)
        if on_round_complete:
            on_round_complete(result, i, total)
        if not result.ok and not continue_on_error:
            break
    return outcome


def regen_insights(year: int, round: int, agent_runner=None) -> dict:
    """Regenerate only the 3 insights from already-ingested data: recompute candidates (so a
    scoring change shows) and re-run the agent. Skips FastF1 ingest and analysis, whose inputs
    haven't changed, so there is no re-download and no cost beyond the agent itself."""
    runner = agent_runner or _default_agent_runner
    with Session(engine) as db:
        weekend_id = _weekend_id(db, year, round)
        if weekend_id is None:
            raise RuntimeError(
                f"No ingested weekend for {year} round {round}. Run run-weekend first."
            )
        compute_candidates(weekend_id, db)
    return _insights({"year": year, "round": round, "weekend_id": weekend_id}, runner)
