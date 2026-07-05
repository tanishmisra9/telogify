"""End-to-end weekend pipeline as a LangGraph: ingest -> analyze -> candidates -> insights.

State holds only primitives so checkpointing stays serializable; the live FastF1
WeekendData never leaves the ingest node. Each phase is idempotent (delete + reinsert),
and FastF1 caches raw data on disk, so re-running a weekend is safe and skips re-downloads.
"""

from typing import TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from sqlmodel import Session

from telogify.agent.graph import build_agent
from telogify.agent.tools import _weekend_id
from telogify.agent.guardrails import flag_unsupported_claims
from telogify.agent.insights import _content_text, extract_trace, parse_insights, persist_insights
from telogify.analysis.attribution import store_attributions
from telogify.analysis.candidates import compute_candidates
from telogify.analysis.constructor_index import build_constructor_index
from telogify.analysis.fingerprints import store_fingerprints
from telogify.config import settings
from telogify.db import engine
from telogify.ingest.loader import load_weekend
from telogify.ingest.quali_character import store_quali_character
from telogify.ingest.deployment import store_deployment
from telogify.ingest.race_control import store_race_control
from telogify.ingest.results import store_results
from telogify.ingest.sectors import store_sector_bests
from telogify.ingest.stints import store_stints
from telogify.ingest.straights import store_straights


class PipelineState(TypedDict, total=False):
    year: int
    round: int
    weekend_id: int
    insight_count: int


def _ingest(state: PipelineState) -> dict:
    with Session(engine) as db:
        data = load_weekend(state["year"], state["round"], db)
        store_straights(data, db)
        store_stints(data, db, fuel_effect=settings.fuel_effect_s_per_lap)
        store_results(data, db)
        store_fingerprints(data, db)
        store_sector_bests(data, db)
        store_quali_character(data, db)
        store_race_control(data, db)
        store_deployment(data, db)
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


def _flag_all(insights: list[dict]) -> dict[int, list[str]]:
    """Flag each insight independently so feedback can name exactly which slot is bad."""
    flagged = {}
    for i, ins in enumerate(insights, start=1):
        text = f"{ins.get('header', '')} {ins.get('explanation_web', '')} {ins.get('explanation_email', '')}"
        phrases = flag_unsupported_claims(text)
        if phrases:
            flagged[i] = phrases
    return flagged


def _insights(state: PipelineState, agent_runner) -> dict:
    """Generate the 3 insights, rejecting and re-prompting on any guardrail violation.
    Nothing is persisted, and the pipeline fails loud, unless a clean set is produced within
    _MAX_INSIGHT_ATTEMPTS: shipping a fabricated claim is worse than shipping nothing."""
    feedback = None
    flagged: dict[int, list[str]] = {}
    for _attempt in range(1, _MAX_INSIGHT_ATTEMPTS + 1):
        messages = agent_runner(state["year"], state["round"], feedback=feedback)
        final = _content_text(messages[-1].content)
        try:
            insights = parse_insights(final)
        except ValueError as e:
            # Malformed output (bad JSON, extra prose, wrong shape) is retryable, not fatal:
            # feed the error back and let the agent re-emit rather than crashing the run.
            feedback = (
                f"Your last message could not be parsed ({e}). Output ONLY a JSON array of "
                "exactly 3 objects with keys header, explanation_web, explanation_email. No "
                "text before or after the array."
            )
            continue
        flagged = _flag_all(insights)
        if not flagged:
            trace = extract_trace(messages)
            with Session(engine) as db:
                rows = persist_insights(state["weekend_id"], insights, trace, db)
            return {"insight_count": len(rows)}
        feedback = (
            "Your last set of 3 insights violated the rules above. Specifically, insight "
            f"slot(s) {sorted(flagged)} used unsupported phrasing: {flagged}. Rewrite ALL 3 "
            "insights from scratch, removing every one of those phrases and any claim like "
            "them, while keeping every number grounded in tool returns. Output the JSON "
            "array again, nothing else."
        )
    raise RuntimeError(
        f"Insight agent kept producing unsupported claims after {_MAX_INSIGHT_ATTEMPTS} "
        f"attempts for {state['year']} round {state['round']}: {flagged}"
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
