import json

import pytest
from langchain_core.messages import AIMessage
from sqlmodel import Session

from telogify.agent.tools import build_tools
from telogify.models import (
    CandidateInsight,
    ConstructorIndex,
    RaceWeekend,
    Session as SessionRow,
    StraightSegment,
)


@pytest.fixture
def seeded(test_engine):
    with Session(test_engine) as db:
        wk = RaceWeekend(
            year=2025, round=11, circuit_name="Spielberg", country="Austria", event_name="Austria"
        )
        db.add(wk)
        db.commit()
        db.refresh(wk)
        race = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
        db.add(race)
        db.commit()
        db.refresh(race)
        db.add(
            StraightSegment(
                session_id=race.id, driver="LEC", drs_zone_id=2,
                max_speed_kmh=330.5, trap_speed_kmh=325.0,
            )
        )
        db.add(
            ConstructorIndex(
                weekend_id=wk.id, constructor="Ferrari", overall_rank=2,
                high_score=-1.2, mid_score=0.4, low_score=0.1, lap_deficit_s=0.35,
            )
        )
        db.add(
            CandidateInsight(
                weekend_id=wk.id, rank=1, category="cross_session", signal_type="cross_session",
                magnitude=12.0, confidence=0.9, robustness_score=1.8,
                source_refs_json={"subject": "Ferrari", "refs": []},
            )
        )
        db.commit()
    return lambda: Session(test_engine)


def _by_name(tools):
    return {t.name: t for t in tools}


def test_bound_tool_reads_exact_db_value(seeded):
    tools = _by_name(build_tools(2025, 11, session_factory=seeded))
    out = json.loads(tools["get_straight_speed"].invoke({"driver": "LEC", "session_type": "R", "drs_zone": 2}))
    assert out["found"] is True
    assert out["max_speed_kmh"] == 330.5
    assert out["max_speed_mph"] == round(330.5 * 0.621371, 1)


def test_tool_call_loop(seeded):
    # Simulate the ReAct loop: model emits a tool call, the bound tool runs, the result
    # comes back as a ToolMessage carrying the exact DB value.
    from langchain_core.messages import ToolMessage

    tools_by_name = _by_name(build_tools(2025, 11, session_factory=seeded))
    ai = AIMessage(
        content="",
        tool_calls=[{"name": "get_candidate_insights", "args": {"n": 5}, "id": "c1", "type": "tool_call"}],
    )

    messages = [ai]
    for call in ai.tool_calls:
        observation = tools_by_name[call["name"]].invoke(call["args"])
        messages.append(ToolMessage(content=observation, tool_call_id=call["id"]))

    payload = json.loads(messages[-1].content)
    assert payload[0]["rank"] == 1
    assert payload[0]["signal_type"] == "cross_session"


def test_constructor_ranking_tool(seeded):
    tools = _by_name(build_tools(2025, 11, session_factory=seeded))
    out = json.loads(tools["get_constructor_ranking"].invoke({}))
    assert out[0]["constructor"] == "Ferrari"
    assert out[0]["overall_rank"] == 2


def test_build_agent_fails_loud_without_api_key(monkeypatch):
    from telogify.agent import graph
    from telogify.config import settings

    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "")
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        graph.build_agent(2025, 11)
