import json

import pytest
from langchain_core.messages import AIMessage
from sqlmodel import Session

from telogify.agent.tools import build_tools
from telogify.models import (
    CandidateInsight,
    ConstructorIndex,
    QualiCharacter,
    RaceWeekend,
    SectorBest,
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
        db.add(
            CandidateInsight(
                weekend_id=wk.id, rank=2, category="quali_character",
                signal_type="quali_top_speed_delta", magnitude=4.0, confidence=1.0,
                robustness_score=1.0, source_refs_json={"subject": "McLaren", "refs": []},
            )
        )
        quali = SessionRow(weekend_id=wk.id, session_type="Q", status="loaded")
        db.add(quali)
        db.commit()
        db.refresh(quali)
        db.add(
            QualiCharacter(
                session_id=quali.id, driver="LEC", constructor="Ferrari", lap_time_s=66.3,
                top_speed_kmh=325.0, min_speed_kmh=71.0, full_throttle_pct=0.64,
                corner_speeds_json={"8": 244.0},
            )
        )
        db.add(
            QualiCharacter(
                session_id=quali.id, driver="NOR", constructor="McLaren", lap_time_s=66.5,
                top_speed_kmh=326.0, min_speed_kmh=72.0, full_throttle_pct=0.54,
                corner_speeds_json={"8": 239.0},
            )
        )
        db.add(SectorBest(session_id=quali.id, driver="LEC", sector=1, best_time_s=20.1))
        db.add(SectorBest(session_id=quali.id, driver="NOR", sector=1, best_time_s=20.4))
        db.commit()
    return lambda: Session(test_engine)


def _by_name(tools):
    return {t.name: t for t in tools}


def test_get_deployment_reports_field_min_and_sorts_ascending(db_session):
    from telogify.models import DeploymentTrace

    wk = RaceWeekend(year=2026, round=9, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    quali = SessionRow(weekend_id=wk.id, session_type="Q", status="loaded")
    db_session.add(quali)
    db_session.commit()
    db_session.refresh(quali)

    db_session.add(DeploymentTrace(session_id=quali.id, driver="LEC", constructor="Ferrari", total_clip_m=375.6, max_clip_m=200.0))
    db_session.add(DeploymentTrace(session_id=quali.id, driver="NOR", constructor="McLaren", total_clip_m=155.9, max_clip_m=90.0))
    db_session.add(DeploymentTrace(session_id=quali.id, driver="VER", constructor="Red Bull Racing", total_clip_m=260.0, max_clip_m=140.0))
    db_session.commit()

    tools = _by_name(build_tools(2026, 9, session_factory=lambda: db_session))
    out = json.loads(tools["get_deployment"].invoke({"driver": "", "session_type": "Q"}))

    # ascending by total_clip_m: field-best (lowest) first, not the old descending order
    assert [r["driver"] for r in out] == ["NOR", "VER", "LEC"]
    # every row carries the true field minimum, computed across the whole field
    assert all(r["field_min_total_clip_m"] == 155.9 for r in out)
    assert all(r["field_min_max_clip_m"] == 90.0 for r in out)

    # filtering by driver must not change the field-wide minimum to just that driver's own value
    filtered = json.loads(tools["get_deployment"].invoke({"driver": "LEC", "session_type": "Q"}))
    assert len(filtered) == 1
    assert filtered[0]["total_clip_m"] == 375.6
    assert filtered[0]["field_min_total_clip_m"] == 155.9


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


def test_get_candidate_insights_filters_by_category(seeded):
    tools = _by_name(build_tools(2025, 11, session_factory=seeded))
    out = json.loads(tools["get_candidate_insights"].invoke({"n": 10, "category": "quali_character"}))
    assert len(out) == 1
    assert out[0]["signal_type"] == "quali_top_speed_delta"


def test_get_quali_character_tool(seeded):
    tools = _by_name(build_tools(2025, 11, session_factory=seeded))
    out = json.loads(tools["get_quali_character"].invoke({}))
    by_constructor = {r["constructor"]: r for r in out["rows"]}
    assert by_constructor["Ferrari"]["drag_label"] == "draggy, high-downforce"
    assert by_constructor["McLaren"]["is_grip_leader"] is True
    assert out["fastest_corner_number"] == 8
    assert out["sector_dominance"][0]["constructor"] == "Ferrari"


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
