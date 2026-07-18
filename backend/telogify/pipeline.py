"""End-to-end weekend pipeline as a LangGraph: ingest -> analyze -> candidates -> insights.

State holds only primitives so checkpointing stays serializable; the live FastF1
WeekendData never leaves the ingest node. Each phase is idempotent (delete + reinsert),
and FastF1 caches raw data on disk, so re-running a weekend is safe and skips re-downloads.
"""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from sqlmodel import Session, select

from telogify.agent.graph import build_agent
from telogify.agent.tools import _weekend_id
from telogify.agent.guardrails import flag_unsupported_claims, format_insight_validation_feedback
from telogify.agent.insights import (
    _content_text,
    _QUALI_REQUIRED_KEYS,
    _REQUIRED_KEYS,
    extract_trace,
    parse_insights,
    persist_insights,
)
from telogify.agent.prompts import PROMPT_VERSION, QUALI_SYSTEM_PROMPT
from telogify.config import configured_llm_label
from telogify.agent.validation import validate_insights
from telogify.analysis.attribution import store_attributions
from telogify.analysis.candidates import compute_candidates
from telogify.analysis.constructor_index import build_constructor_index
from telogify.analysis.fingerprints import store_fingerprints
from telogify.analysis.schedule import completed_rounds, fetch_season_schedule
from telogify.db import engine
from telogify.ingest.accel_samples import store_accel_samples
from telogify.ingest.loader import load_weekend
from telogify.ingest.quali_character import store_quali_character
from telogify.ingest.quali_trace import store_quali_traces
from telogify.ingest.deployment import store_deployment
from telogify.ingest.race_control import store_race_control
from telogify.ingest.results import store_results
from telogify.ingest.sectors import store_sector_bests
from telogify.ingest.stints import store_stints
from telogify.ingest.straights import store_straights
from telogify.models import Insight, QualiInsight
from telogify.models import Session as SessionModel

logger = logging.getLogger("telogify.insights")


class PipelineState(TypedDict, total=False):
    year: int
    round: int
    weekend_id: int
    session_types: list[str]
    insight_count: int
    quali_insight_count: int


def _ingest(state: PipelineState) -> dict:
    with Session(engine) as db:
        data = load_weekend(state["year"], state["round"], db)
        store_straights(data, db)
        store_stints(data, db)
        store_results(data, db)
        store_fingerprints(data, db)
        store_sector_bests(data, db)
        store_quali_character(data, db)
        store_quali_traces(data, db)
        store_race_control(data, db)
        store_deployment(data, db)
        store_accel_samples(data, db)
        return {"weekend_id": data.weekend.id, "session_types": sorted(data.sessions)}


def _has_quali_or_race(state: PipelineState) -> bool:
    session_types = state.get("session_types", ())
    return "Q" in session_types or "R" in session_types


def _analyze(state: PipelineState) -> dict:
    if not _has_quali_or_race(state):
        return {}
    with Session(engine) as db:
        store_attributions(state["weekend_id"], db)
        build_constructor_index(state["weekend_id"], db)
    return {}


def _candidates(state: PipelineState) -> dict:
    if not _has_quali_or_race(state):
        return {}
    with Session(engine) as db:
        compute_candidates(state["weekend_id"], db)
    return {}


def _ingested_session_types(db: Session, weekend_id: int) -> set[str]:
    rows = db.exec(select(SessionModel).where(SessionModel.weekend_id == weekend_id)).all()
    return {r.session_type for r in rows}


_MAX_INSIGHT_ATTEMPTS = 3


def _flag_all(insights: list[dict]) -> dict[int, list[str]]:
    """Flag each insight independently so feedback can name exactly which slot is bad."""
    flagged = {}
    for i, ins in enumerate(insights, start=1):
        text = f"{ins.get('header', '')} {ins.get('explanation_web', '')} {ins.get('explanation_email', '')}"
        phrases = flag_unsupported_claims(text)
        if phrases:
            flagged[i] = phrases
    return flagged


def _merge_flags(*maps: dict[int, list[str]]) -> dict[int, list[str]]:
    merged: dict[int, list[str]] = {}
    for m in maps:
        for slot, issues in m.items():
            merged.setdefault(slot, []).extend(issues)
    return merged


def _insights(
    state: PipelineState,
    agent_runner,
    *,
    count: int = 3,
    model: type = Insight,
    required_keys: tuple[str, ...] = _REQUIRED_KEYS,
    result_key: str = "insight_count",
    allow_qualifying_only: bool = False,
) -> dict:
    """Generate `count` insights, rejecting and re-prompting on any guardrail violation.
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
            insights = parse_insights(final, count=count, required_keys=required_keys)
        except ValueError as e:
            parse_failures += 1
            last_parse_error = str(e)
            # Malformed output (bad JSON, extra prose, wrong shape) is retryable, not fatal:
            # feed the error back and let the agent re-emit rather than crashing the run.
            feedback = (
                f"Your last message could not be parsed ({e}). Your final message must "
                f"contain a raw JSON array of exactly {count} objects with keys "
                f"{', '.join(required_keys)}. Do not wrap the array in Markdown backticks or "
                "add conversational filler."
            )
            continue
        trace = extract_trace(messages)
        flagged = _merge_flags(
            _flag_all(insights),
            validate_insights(insights, trace, allow_qualifying_only=allow_qualifying_only),
        )
        if not flagged:
            trace = extract_trace(messages)
            with Session(engine) as db:
                rows = persist_insights(
                    state["weekend_id"],
                    insights,
                    trace,
                    db,
                    model=model,
                    count=count,
                    model_used=configured_llm_label(),
                    prompt_version=PROMPT_VERSION,
                )
            return {result_key: len(rows)}
        for slot in flagged:
            ins = insights[slot - 1]
            logger.info("slot %d header: %r", slot, ins.get("header"))
            logger.info("slot %d body: %r", slot, ins.get("explanation_web"))
        deployment_calls = [e for e in trace if e.get("tool") == "get_deployment"]
        if deployment_calls:
            logger.info(
                "get_deployment calls: %r",
                [(c.get("args"), str(c.get("result"))[:300]) for c in deployment_calls],
            )
        logger.info(
            "%s round %s attempt %d rejected: %s", state["year"], state["round"], _attempt, flagged
        )
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


def _quali_insights(state: PipelineState, agent_runner) -> dict:
    """The 2 qualifying car-character insights: same hard gate as `_insights`, targeting
    QualiInsight instead of Insight."""
    return _insights(
        state,
        agent_runner,
        count=2,
        model=QualiInsight,
        required_keys=_QUALI_REQUIRED_KEYS,
        result_key="quali_insight_count",
        allow_qualifying_only=True,
    )


def _default_agent_runner(year: int, round: int, feedback: str | None = None) -> list:
    agent = build_agent(year, round)
    task = f"Write the 3 insights for {year} round {round}."
    if feedback:
        task = f"{task}\n\n{feedback}"
    result = agent.invoke(
        {"messages": [("user", task)]},
        config={"configurable": {"thread_id": f"agent-{year}-{round}"}},
    )
    return result["messages"]


def _default_quali_agent_runner(year: int, round: int, feedback: str | None = None) -> list:
    agent = build_agent(year, round, system_prompt=QUALI_SYSTEM_PROMPT)
    task = f"Write the 2 qualifying car-character insights for {year} round {round}."
    if feedback:
        task = f"{task}\n\n{feedback}"
    result = agent.invoke(
        {"messages": [("user", task)]},
        config={"configurable": {"thread_id": f"quali-agent-{year}-{round}"}},
    )
    return result["messages"]


def build_pipeline(agent_runner, quali_agent_runner):
    g = StateGraph(PipelineState)
    g.add_node("ingest", _ingest)
    g.add_node("analyze", _analyze)
    g.add_node("candidates", _candidates)
    g.add_node(
        "insights",
        lambda s: _insights(s, agent_runner) if "R" in s.get("session_types", ()) else {},
    )
    g.add_node(
        "quali_insights",
        lambda s: _quali_insights(s, quali_agent_runner) if "Q" in s.get("session_types", ()) else {},
    )
    g.add_edge(START, "ingest")
    g.add_edge("ingest", "analyze")
    g.add_edge("analyze", "candidates")
    g.add_edge("candidates", "insights")
    g.add_edge("insights", "quali_insights")
    g.add_edge("quali_insights", END)
    return g.compile(checkpointer=MemorySaver())


def run_weekend(year: int, round: int, agent_runner=None, quali_agent_runner=None) -> PipelineState:
    pipeline = build_pipeline(
        agent_runner or _default_agent_runner,
        quali_agent_runner or _default_quali_agent_runner,
    )
    return pipeline.invoke(
        {"year": year, "round": round},
        config={"configurable": {"thread_id": f"weekend-{year}-{round}"}},
    )


def run_ingest(year: int, round: int) -> PipelineState:
    """Ingest-only entry point: re-run the FastF1 ingest node for one weekend, with no
    analysis, no candidates, and no LLM call (zero API spend). Every extractor is idempotent
    (delete + reinsert per session) and FastF1's disk cache makes re-runs CPU-bound, so this
    is the cheap path after an ingest extractor changes."""
    state: PipelineState = {"year": year, "round": round}
    return {**state, **_ingest(state)}


@dataclass
class RoundResult:
    round: int
    ok: bool
    insight_count: int = 0
    quali_insight_count: int = 0
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
    quali_agent_runner=None,
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
            state = run_weekend(year, rnd, agent_runner=agent_runner, quali_agent_runner=quali_agent_runner)
            result = RoundResult(
                round=rnd,
                ok=True,
                insight_count=state.get("insight_count", 0),
                quali_insight_count=state.get("quali_insight_count", 0),
            )
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
    quali_agent_runner=None,
    now: datetime | None = None,
    continue_on_error: bool = True,
    max_workers: int = 4,
    on_round_start: Callable[[int, int, int], None] | None = None,
    on_round_complete: Callable[[RoundResult, int, int], None] | None = None,
) -> SeasonRunResult:
    """Regenerate insights for every completed round in a season (LLM only, no FastF1 ingest).

    Rounds are independent (own DB rows, own Session), so they run on a thread pool of
    `max_workers` to overlap the LLM latency that dominates each round. `on_round_complete`
    fires in completion order (its index is a done-counter, not the round position); results
    are sorted back to round order before returning.
    """
    rounds = season_rounds(year, now=now)
    outcome = SeasonRunResult(year=year, rounds=rounds)
    total = len(rounds)
    if not rounds:
        return outcome

    def _work(rnd: int, index: int) -> RoundResult:
        if on_round_start:
            on_round_start(rnd, index, total)
        try:
            state = regen_insights(year, rnd, agent_runner=agent_runner, quali_agent_runner=quali_agent_runner)
            return RoundResult(
                round=rnd,
                ok=True,
                insight_count=state.get("insight_count", 0),
                quali_insight_count=state.get("quali_insight_count", 0),
            )
        except Exception as exc:
            return RoundResult(round=rnd, ok=False, error=str(exc))

    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, total))) as pool:
        futures = {pool.submit(_work, rnd, i): rnd for i, rnd in enumerate(rounds, start=1)}
        done = 0
        for fut in as_completed(futures):
            result = fut.result()
            done += 1
            outcome.results.append(result)
            if on_round_complete:
                on_round_complete(result, done, total)
            if not result.ok and not continue_on_error:
                for pending in futures:
                    pending.cancel()
                break

    outcome.results.sort(key=lambda r: r.round)
    return outcome


def regen_insights(year: int, round: int, agent_runner=None, quali_agent_runner=None) -> dict:
    """Regenerate whichever of the 3 race insights / 2 qualifying insights the ingested data
    supports, from already-ingested data: recompute candidates (so a scoring change shows) and
    re-run the relevant agent(s). Skips FastF1 ingest and analysis, whose inputs haven't
    changed, so there is no re-download and no cost beyond the agents themselves.

    Race insights only run once the race session is ingested; qualifying insights only run once
    the qualifying session is ingested (mid-weekend, that may be all there is yet). If neither
    is ingested, there is nothing to regenerate and this raises loud rather than silently doing
    nothing. If the qualifying insights fail their guardrail/validation gate, the RuntimeError
    propagates even though the race insights already persisted this run: each insight batch is
    its own hard gate, same "never ship a fabricated claim" rule."""
    runner = agent_runner or _default_agent_runner
    quali_runner = quali_agent_runner or _default_quali_agent_runner
    with Session(engine) as db:
        weekend_id = _weekend_id(db, year, round)
        if weekend_id is None:
            raise RuntimeError(
                f"No ingested weekend for {year} round {round}. Run run-weekend first."
            )
        session_types = _ingested_session_types(db, weekend_id)
        if "Q" not in session_types and "R" not in session_types:
            raise RuntimeError(
                f"{year} round {round} has no qualifying or race data ingested yet; "
                "nothing to regenerate insights from. Run run-weekend once a session has "
                "completed."
            )
        compute_candidates(weekend_id, db)
    state: PipelineState = {"year": year, "round": round, "weekend_id": weekend_id}
    result: dict = {"session_types": sorted(session_types)}
    if "R" in session_types:
        result.update(_insights(state, runner))
    if "Q" in session_types:
        result.update(_quali_insights(state, quali_runner))
    return result
