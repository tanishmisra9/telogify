import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from telogify.api.main import app
from telogify.db import get_session
from telogify.models import (
    Insight,
    QualiCharacter,
    RaceWeekend,
    SectorBest,
    Session as SessionRow,
    SessionResult,
    StraightSegment,
    Stint,
    Subscriber,
)


@pytest.fixture
def client(test_engine):
    def override():
        with Session(test_engine) as s:
            yield s

    app.dependency_overrides[get_session] = override
    with Session(test_engine) as db:
        wk = RaceWeekend(
            year=2025, round=11, circuit_name="Spielberg", country="Austria",
            event_name="Austrian Grand Prix",
        )
        db.add(wk)
        db.commit()
        db.refresh(wk)

        fp1 = SessionRow(weekend_id=wk.id, session_type="FP1", status="loaded")
        quali = SessionRow(weekend_id=wk.id, session_type="Q", status="loaded")
        race = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
        db.add(fp1)
        db.add(quali)
        db.add(race)
        db.commit()
        db.refresh(fp1)
        db.refresh(quali)
        db.refresh(race)

        db.add(SessionResult(session_id=race.id, position=1, driver="NOR", constructor="McLaren", gap_to_leader=0.0, laps=71.0, status="Finished"))
        db.add(SessionResult(session_id=race.id, position=2, driver="LEC", constructor="Ferrari", gap_to_leader=2.5, laps=71.0, status="Finished"))
        db.add(SessionResult(session_id=race.id, position=3, driver="ALO", constructor="Aston Martin", gap_to_leader=None, laps=68.0, status="Lapped"))
        db.add(Stint(session_id=race.id, driver="NOR", stint_number=1, compound="MEDIUM", lap_start=1, lap_end=20, avg_pace=70.1, lap_times_json=[70.5, 70.0, 69.9], tyre_ages_json=[1, 2, 3]))
        db.add(Stint(
            session_id=race.id, driver="LEC", stint_number=1, compound="MEDIUM", lap_start=1, lap_end=6,
            avg_pace=92.25, lap_times_json=[92.0, 92.1, 92.2, 92.3, 92.4, 92.5], tyre_ages_json=[1, 2, 3, 4, 5, 6],
        ))

        # Practice: sectors + top speeds (FP1). LEC quicker in S1, NOR quicker in S2.
        db.add(SectorBest(session_id=fp1.id, driver="NOR", sector=1, best_time_s=30.0))
        db.add(SectorBest(session_id=fp1.id, driver="LEC", sector=1, best_time_s=29.8))
        db.add(SectorBest(session_id=fp1.id, driver="NOR", sector=2, best_time_s=40.0))
        db.add(SectorBest(session_id=fp1.id, driver="LEC", sector=2, best_time_s=40.2))
        db.add(StraightSegment(session_id=fp1.id, driver="NOR", drs_zone_id=0, max_speed_kmh=320.0, trap_speed_kmh=318.0))
        db.add(StraightSegment(session_id=fp1.id, driver="LEC", drs_zone_id=0, max_speed_kmh=325.0, trap_speed_kmh=322.0))

        # Qualifying: car character + sector dominance. LEC quicker in S1 here too.
        db.add(SectorBest(session_id=quali.id, driver="NOR", sector=1, best_time_s=29.5))
        db.add(SectorBest(session_id=quali.id, driver="LEC", sector=1, best_time_s=29.3))
        db.add(QualiCharacter(
            session_id=quali.id, driver="NOR", constructor="McLaren", lap_time_s=80.0,
            top_speed_kmh=320.0, min_speed_kmh=90.0, full_throttle_pct=0.55,
            corner_speeds_json={"5": 230.0},
        ))
        db.add(QualiCharacter(
            session_id=quali.id, driver="LEC", constructor="Ferrari", lap_time_s=79.8,
            top_speed_kmh=315.0, min_speed_kmh=95.0, full_throttle_pct=0.62,
            corner_speeds_json={"5": 245.0},
        ))
        # 4 more teams, slowest last, so top-N trimming has something to trim.
        for driver, constructor, lap_time in [
            ("ALB", "Williams", 81.0),
            ("GAS", "Alpine", 81.5),
            ("BOR", "Audi", 82.0),
            ("ALO", "Aston Martin", 82.5),
        ]:
            db.add(QualiCharacter(
                session_id=quali.id, driver=driver, constructor=constructor, lap_time_s=lap_time,
                top_speed_kmh=310.0, min_speed_kmh=90.0, full_throttle_pct=0.5,
                corner_speeds_json={"5": 220.0},
            ))

        db.add(Insight(weekend_id=wk.id, slot=1, header="H1", explanation_web="W1", explanation_email="E1", source_tool_calls_json=[]))
        db.commit()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_list_weekends(client):
    r = client.get("/weekends")
    assert r.status_code == 200
    assert r.json()[0]["event_name"] == "Austrian Grand Prix"


def test_weekend_detail_404(client):
    assert client.get("/weekends/1999/1").status_code == 404


def test_insights(client):
    r = client.get("/weekends/2025/11/insights")
    assert [i["header"] for i in r.json()] == ["H1"]


def test_latest_insight_picks_recent_weekend_slot1(client, test_engine):
    # Fixture seeds 2025 R11 (H1). Add a newer weekend with two insights; latest = its slot 1.
    with Session(test_engine) as db:
        wk = RaceWeekend(year=2026, round=2, circuit_name="X", country="Y", event_name="New GP")
        db.add(wk)
        db.commit()
        db.refresh(wk)
        db.add(Insight(weekend_id=wk.id, slot=2, header="secondary", explanation_web="w2", explanation_email="e2", source_tool_calls_json=[]))
        db.add(Insight(weekend_id=wk.id, slot=1, header="primary", explanation_web="w1", explanation_email="e1", source_tool_calls_json=[]))
        db.commit()
    body = client.get("/insights/latest").json()
    assert body["event_name"] == "New GP"
    assert body["slot"] == 1
    assert body["header"] == "primary"


def test_next_race_picks_soonest_future(client, monkeypatch):
    from datetime import datetime, timedelta

    from telogify.analysis.schedule import Event
    from telogify.api import routes

    now = datetime.utcnow()
    events = (
        Event(round=1, name="Past GP", date=now - timedelta(days=30)),
        Event(round=9, name="Silverstone", date=now + timedelta(days=10)),
        Event(round=10, name="Hungaroring", date=now + timedelta(days=30)),
    )
    monkeypatch.setattr(routes, "_schedule_events", lambda year: events if year == now.year else ())
    body = client.get("/next-race").json()
    assert body["event_name"] == "Silverstone"
    assert body["round"] == 9
    assert body["date_utc"].endswith("Z")


def test_pace(client):
    data = client.get("/weekends/2025/11/pace").json()
    # Chart path: mean-ranked, lap 1 excluded; season ranking still uses median elsewhere.
    assert "drivers" in data and "constructors" in data
    assert data["rank_metric"] == "mean"
    assert data["excludes_lap_1"] is True
    drivers = {d["id"]: d for d in data["drivers"]}
    assert set(drivers) == {"NOR", "LEC"}
    assert drivers["NOR"]["team"] == "McLaren"
    assert drivers["NOR"]["gap_to_fastest_s"] == 0.0
    assert drivers["NOR"]["stats"]["n_laps"] == 2  # lap 1 excluded from [70.5, 70.0, 69.9]
    constructors = {c["id"]: c for c in data["constructors"]}
    assert set(constructors) == {"McLaren", "Ferrari"}
    # Both drivers seeded with a single stint -> zero stops, zero spread.
    assert data["stop_counts"] == {"NOR": 0, "LEC": 0}
    assert data["stop_count_spread"] == 0


def test_sessions(client):
    rows = client.get("/weekends/2025/11/sessions").json()
    assert [r["session_type"] for r in rows] == ["FP1", "Q", "R"]


def test_sectors(client):
    data = client.get("/weekends/2025/11/sectors").json()
    assert data["indicative"] is True
    by_key = {(d["driver"], d["sector"]): d for d in data["drivers"]}
    assert by_key[("LEC", 1)]["best_time_s"] == 29.8
    assert by_key[("LEC", 1)]["constructor"] == "Ferrari"
    assert by_key[("LEC", 1)]["session_type"] == "FP1"

    dominance = {d["sector"]: d for d in data["dominance"]}
    assert dominance[1]["constructor"] == "Ferrari"  # 29.8 < 30.0
    assert dominance[2]["constructor"] == "McLaren"  # 40.0 < 40.2


def test_topspeeds(client):
    data = client.get("/weekends/2025/11/topspeeds").json()
    assert data["indicative"] is True
    top = data["drivers"][0]
    assert top["driver"] == "LEC"
    assert top["constructor"] == "Ferrari"
    assert top["max_speed_kmh"] == 325.0
    assert abs(top["max_speed_mph"] - 325.0 * 0.621371) < 1e-6


def test_quali_character(client):
    data = client.get("/weekends/2025/11/quali-character").json()
    assert data["session_type"] == "Q"
    # 6 teams are seeded (Ferrari, McLaren, Williams, Alpine, Audi, Aston Martin); the
    # slowest (Aston Martin) must be trimmed by TOP_TEAMS_N=5.
    rows = {r["constructor"]: r for r in data["rows"]}
    assert set(rows) == {"Ferrari", "McLaren", "Williams", "Alpine", "Audi"}
    assert "Aston Martin" not in rows
    assert rows["Ferrari"]["driver"] == "LEC"
    # Only corner 5 has any data, so it must be the one picked as "the fastest corner".
    assert data["fastest_corner_number"] == 5

    dominance = {d["sector"]: d for d in data["sector_dominance"]}
    assert dominance[1]["constructor"] == "Ferrari"  # 29.3 < 29.5


def test_degradation(client):
    data = client.get("/weekends/2025/11/degradation").json()
    fits = {f["constructor"]: f for f in data["fits"]}
    assert "Ferrari" in fits
    assert abs(fits["Ferrari"]["slope_s_per_lap"] - 0.1) < 1e-6
    # NOR/McLaren only has 3 laps, below the minimum sample size for a fit.
    assert "McLaren" not in fits


def test_results(client):
    rows = client.get("/weekends/2025/11/results").json()
    assert [r["driver"] for r in rows] == ["NOR", "LEC", "ALO"]
    assert rows[0]["gap_label"] == "leader"
    assert rows[1]["gap_label"] == "+2.5s"
    assert rows[2]["gap_label"] == "+3 Laps"
    assert rows[0]["points"] == 25


def test_sprint_session_endpoints(client, test_engine):
    with Session(test_engine) as db:
        wk = db.exec(
            select(RaceWeekend).where(RaceWeekend.year == 2025, RaceWeekend.round == 11)
        ).first()
        sq = SessionRow(weekend_id=wk.id, session_type="SQ", status="loaded")
        sprint = SessionRow(weekend_id=wk.id, session_type="SPRINT", status="loaded")
        db.add(sq)
        db.add(sprint)
        db.commit()
        db.refresh(sq)
        db.refresh(sprint)

        db.add(SectorBest(session_id=sq.id, driver="NOR", sector=1, best_time_s=29.0))
        db.add(StraightSegment(session_id=sq.id, driver="NOR", drs_zone_id=0, max_speed_kmh=330.0, trap_speed_kmh=328.0))
        db.add(SessionResult(session_id=sq.id, position=1, driver="NOR", constructor="McLaren", gap_to_leader=0.0, laps=None, status="Finished"))
        db.add(SessionResult(session_id=sprint.id, position=1, driver="VER", constructor="Red Bull", gap_to_leader=0.0, laps=19.0, status="Finished"))
        db.add(Stint(
            session_id=sprint.id, driver="VER", stint_number=1, compound="MEDIUM", lap_start=1, lap_end=19,
            avg_pace=90.0, lap_times_json=[90.0, 90.1, 90.2, 90.3, 90.4, 90.5], tyre_ages_json=[1, 2, 3, 4, 5, 6],
        ))
        db.commit()

    sprint_rows = client.get("/weekends/2025/11/results?session=SPRINT").json()
    assert sprint_rows[0]["driver"] == "VER"
    assert sprint_rows[0]["points"] == 8

    summary = client.get("/weekends/2025/11/session-summary?session=SQ").json()
    assert summary["session_type"] == "SQ"
    assert summary["order"][0]["driver"] == "NOR"
    assert summary["sectors"]["drivers"][0]["best_time_s"] == 29.0

    assert client.get("/weekends/2025/11/pace?session=SPRINT").json()["drivers"][0]["id"] == "VER"


def test_subscribe_and_dedupe(client, test_engine):
    assert client.post("/subscribe", json={"email": "a@b.com", "followed_constructor": "Ferrari"}).json()["status"] == "subscribed"
    assert client.post("/subscribe", json={"email": "a@b.com"}).json()["status"] == "already_subscribed"
    with Session(test_engine) as db:
        from sqlmodel import select
        subs = db.exec(select(Subscriber)).all()
    assert len(subs) == 1 and subs[0].followed_constructor == "Ferrari"
