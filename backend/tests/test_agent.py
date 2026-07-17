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


def test_get_race_deployment_character_reports_at_speed_accel_and_rank(db_session):
    from telogify.models import AccelSample

    wk = RaceWeekend(year=2026, round=9, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    race = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
    db_session.add(race)
    db_session.commit()
    db_session.refresh(race)

    speeds = [150.0, 160.0, 170.0, 180.0, 190.0, 200.0, 210.0, 220.0, 230.0, 240.0, 250.0]

    def accels(slope: float, intercept: float) -> list[float]:
        return [slope * s + intercept for s in speeds]

    # A: steep drop-off (holds acceleration worst). B: flattest (holds best). C: in between.
    db_session.add(AccelSample(session_id=race.id, driver="VER", constructor="A", speed_kmh_json=speeds, longitudinal_accel_ms2_json=accels(-0.05, 10.0)))
    db_session.add(AccelSample(session_id=race.id, driver="NOR", constructor="B", speed_kmh_json=speeds, longitudinal_accel_ms2_json=accels(-0.01, 2.0)))
    db_session.add(AccelSample(session_id=race.id, driver="LEC", constructor="C", speed_kmh_json=speeds, longitudinal_accel_ms2_json=accels(-0.03, 6.0)))
    db_session.commit()

    tools = _by_name(build_tools(2026, 9, session_factory=lambda: db_session))
    out = json.loads(tools["get_race_deployment_character"].invoke({"constructor": ""}))
    by_constructor = {r["constructor"]: r for r in out}

    assert by_constructor["A"]["accel_at_150_ms2"] == pytest.approx(2.5)
    assert by_constructor["A"]["accel_at_250_ms2"] == pytest.approx(-2.5)
    assert by_constructor["B"]["accel_at_150_ms2"] == pytest.approx(0.5)
    assert by_constructor["B"]["accel_at_250_ms2"] == pytest.approx(-0.5)
    # Rank 1 = best accel_at_250 (holds acceleration best at the top of the band).
    assert by_constructor["B"]["rank"] == 1
    assert by_constructor["C"]["rank"] == 2
    assert by_constructor["A"]["rank"] == 3
    assert by_constructor["A"]["field_average_accel_at_250_ms2"] == pytest.approx(-1.5)

    filtered = json.loads(tools["get_race_deployment_character"].invoke({"constructor": "B"}))
    assert len(filtered) == 1 and filtered[0]["constructor"] == "B"


def test_compare_stint_pace_reports_final_stint_delta(db_session):
    from telogify.models import Stint

    wk = RaceWeekend(year=2026, round=8, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    race = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
    db_session.add(race)
    db_session.commit()
    db_session.refresh(race)

    # ANT: two stints, final stint (hard) averages 70.424s -- the quickest final stint.
    db_session.add(Stint(session_id=race.id, driver="ANT", stint_number=1, compound="MEDIUM", lap_start=1, lap_end=20, avg_pace=71.0))
    db_session.add(Stint(session_id=race.id, driver="ANT", stint_number=2, compound="HARD", lap_start=21, lap_end=50, avg_pace=70.424))
    # VER: one stint, final stint (hard) averages 70.670s.
    db_session.add(Stint(session_id=race.id, driver="VER", stint_number=1, compound="HARD", lap_start=1, lap_end=50, avg_pace=70.670))
    # RUS: final stint 70.889s, no data at all for a code not requested (COL) to prove filtering.
    db_session.add(Stint(session_id=race.id, driver="RUS", stint_number=1, compound="HARD", lap_start=1, lap_end=50, avg_pace=70.889))
    db_session.commit()

    tools = _by_name(build_tools(2026, 8, session_factory=lambda: db_session))
    out = json.loads(tools["compare_stint_pace"].invoke({"drivers": "ANT,VER,RUS", "session_type": "R"}))
    by_driver = {r["driver"]: r for r in out}

    assert by_driver["ANT"]["final_stint_delta_vs_best_s_per_lap"] == 0.0
    assert by_driver["VER"]["final_stint_delta_vs_best_s_per_lap"] == pytest.approx(0.246)
    assert by_driver["RUS"]["final_stint_delta_vs_best_s_per_lap"] == pytest.approx(0.465)
    assert len(by_driver["ANT"]["stints"]) == 2
    assert by_driver["ANT"]["stints"][-1]["avg_pace_s"] == 70.424


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


def test_constructor_ranking_reports_gap_to_team_ahead(db_session):
    wk = RaceWeekend(year=2026, round=9, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)

    db_session.add(ConstructorIndex(weekend_id=wk.id, constructor="Mercedes", overall_rank=1, lap_deficit_s=0.0))
    db_session.add(ConstructorIndex(weekend_id=wk.id, constructor="Ferrari", overall_rank=2, lap_deficit_s=0.2))
    db_session.add(ConstructorIndex(weekend_id=wk.id, constructor="Haas", overall_rank=3, lap_deficit_s=1.5))
    db_session.commit()

    tools = _by_name(build_tools(2026, 9, session_factory=lambda: db_session))
    out = json.loads(tools["get_constructor_ranking"].invoke({}))
    by_constructor = {r["constructor"]: r for r in out}

    # The fastest team has no team ahead of it: 0.0, not a self-comparison artifact.
    assert by_constructor["Mercedes"]["gap_to_team_ahead_s"] == 0.0
    assert by_constructor["Ferrari"]["gap_to_team_ahead_s"] == pytest.approx(0.2)
    # Haas's real rival is Ferrari (1.3s away), not Mercedes (1.5s away).
    assert by_constructor["Haas"]["gap_to_team_ahead_s"] == pytest.approx(1.3)
    assert by_constructor["Haas"]["race_pace_gap_s"] == pytest.approx(1.5)


def test_compare_car_speed_profile_reports_cornering_top_speed_and_sectors(db_session):
    from telogify.models import Attribution, SessionResult

    wk = RaceWeekend(year=2026, round=9, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    race = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
    db_session.add(race)
    db_session.commit()
    db_session.refresh(race)

    db_session.add(SessionResult(session_id=race.id, driver="LEC", constructor="Ferrari"))
    db_session.add(SessionResult(session_id=race.id, driver="RUS", constructor="Mercedes"))

    # Two confident corners favoring Ferrari, one unreliable (low confidence) that must drop.
    db_session.add(Attribution(session_id=race.id, corner_number=1, speed_class="low", constructor_a="Ferrari", constructor_b="Mercedes", delta_s=3.0, confidence=0.9))
    db_session.add(Attribution(session_id=race.id, corner_number=3, speed_class="low", constructor_a="Mercedes", constructor_b="Ferrari", delta_s=-1.0, confidence=0.8))
    db_session.add(Attribution(session_id=race.id, corner_number=9, speed_class="high", constructor_a="Ferrari", constructor_b="Mercedes", delta_s=5.0, confidence=0.1))

    db_session.add(StraightSegment(session_id=race.id, driver="LEC", drs_zone_id=0, max_speed_kmh=340.0))
    db_session.add(StraightSegment(session_id=race.id, driver="RUS", drs_zone_id=0, max_speed_kmh=345.0))

    db_session.add(SectorBest(session_id=race.id, driver="LEC", sector=1, best_time_s=28.1))
    db_session.add(SectorBest(session_id=race.id, driver="RUS", sector=1, best_time_s=28.4))
    db_session.commit()

    tools = _by_name(build_tools(2026, 9, session_factory=lambda: db_session))
    out = json.loads(
        tools["compare_car_speed_profile"].invoke(
            {"constructor_a": "Ferrari", "constructor_b": "Mercedes", "session_type": "R"}
        )
    )

    assert out["found"] is True
    low = next(c for c in out["cornering_by_speed_class"] if c["speed_class"] == "low")
    assert low["n_corners"] == 2
    assert low["avg_delta_kmh"] == pytest.approx(4.0 / 2)  # +3.0 and +1.0 (sign-flipped row)
    assert low["corner_numbers"] == [1, 3]
    assert all(c["speed_class"] != "high" for c in out["cornering_by_speed_class"])  # low-confidence corner dropped

    assert out["top_speed_delta_kmh"] == pytest.approx(-5.0)  # Ferrari 340 - Mercedes 345
    assert out["sector_deltas_s"] == [{"sector": 1, "delta_s": pytest.approx(-0.3)}]
    assert out["confident"] is True


def test_build_agent_fails_loud_without_api_key(monkeypatch):
    from telogify.agent import graph
    from telogify.config import settings

    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "")
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        graph.build_agent(2025, 11)
