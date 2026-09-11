import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from telogify.api.main import app
from telogify.db import get_session
from telogify.models import (
    Insight,
    QualiCharacter,
    QualiInsight,
    RaceWeekend,
    SeasonDeploymentInsight,
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
        db.add(QualiInsight(weekend_id=wk.id, slot=1, team="Ferrari", header="QH1", explanation_web="QW1", explanation_email="QE1", source_tool_calls_json=[]))
        db.commit()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_list_weekends(client):
    r = client.get("/weekends")
    assert r.status_code == 200
    assert r.json()[0]["event_name"] == "Austrian Grand Prix"


def test_weekend_detail_404(client, monkeypatch):
    # Round not ingested AND not on the (monkeypatched, so no live FastF1 call) calendar either.
    from telogify.api import routes

    monkeypatch.setattr(routes, "_schedule_events", lambda year: ())
    assert client.get("/weekends/1999/1").status_code == 404


def test_weekend_detail_falls_back_to_schedule_for_unraced_round(client, monkeypatch):
    """A round not yet ingested but on the season calendar still renders (as a "coming soon"
    shape) instead of 404ing, so the weekend page can show it with a countdown."""
    from datetime import datetime

    from telogify.analysis.schedule import Event
    from telogify.api import routes

    events = (
        Event(round=12, name="Future GP", date=datetime(2025, 8, 1), country="Neverland", location="Nowhere City"),
    )
    monkeypatch.setattr(routes, "_schedule_events", lambda year: events if year == 2025 else ())
    r = client.get("/weekends/2025/12")
    assert r.status_code == 200
    assert r.json() == {
        "id": None,
        "year": 2025,
        "round": 12,
        "event_name": "Future GP",
        "circuit_name": "Nowhere City",
        "country": "Neverland",
        "race_laps": None,
    }


def test_weekend_detail_includes_race_laps(client):
    """race_laps is the WINNER's classified laps (fixture seeds NOR at position 1, 71.0 laps),
    never a non-winner's -- a retiree's count is a known FastF1 undercount."""
    body = client.get("/weekends/2025/11").json()
    assert body["race_laps"] == 71


def test_insights(client):
    r = client.get("/weekends/2025/11/insights")
    assert [i["header"] for i in r.json()] == ["H1"]


def test_quali_insights(client):
    r = client.get("/weekends/2025/11/quali-insights")
    assert r.json() == [{"slot": 1, "team": "Ferrari", "header": "QH1", "explanation_web": "QW1"}]


def test_quali_insights_filters_by_session(client, test_engine):
    """Q and SQ insights share the QualiInsight table -- ?session must scope to one, never
    surfacing the other's rows under the wrong label."""
    with Session(test_engine) as db:
        wk = db.exec(select(RaceWeekend).where(RaceWeekend.year == 2025, RaceWeekend.round == 11)).first()
        db.add(QualiInsight(
            weekend_id=wk.id, slot=1, session_type="SQ", team="McLaren",
            header="SQH1", explanation_web="SQW1", explanation_email="SQE1",
        ))
        db.commit()

    r_q = client.get("/weekends/2025/11/quali-insights?session=Q")
    assert [i["header"] for i in r_q.json()] == ["QH1"]

    r_sq = client.get("/weekends/2025/11/quali-insights?session=SQ")
    assert [i["header"] for i in r_sq.json()] == ["SQH1"]


def test_quali_insights_rejects_invalid_session(client):
    r = client.get("/weekends/2025/11/quali-insights?session=R")
    assert r.status_code == 422


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
    # Median-ranked, lap 1 excluded: the single canonical ranking, shared with the agent.
    assert "drivers" in data and "constructors" in data
    assert data["rank_metric"] == "median"
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


def test_sessions(client, monkeypatch):
    # session_schedule hits live FastF1; monkeypatch it for a deterministic full-calendar
    # response, same pattern as test_next_race_picks_soonest_future's _schedule_events.
    from telogify.api import routes

    monkeypatch.setattr(
        routes,
        "session_schedule",
        lambda year, round: [
            ("FP1", "Practice 1", None),
            ("FP2", "Practice 2", None),
            ("FP3", "Practice 3", None),
            ("Q", "Qualifying", None),
            ("R", "Race", None),
        ],
    )
    rows = client.get("/weekends/2025/11/sessions").json()
    by_type = {r["session_type"]: r for r in rows}
    assert [r["session_type"] for r in rows] == ["FP1", "FP2", "FP3", "Q", "R"]
    # FP1/Q/R were ingested by the fixture; FP2/FP3 are on the calendar but not yet ingested.
    assert by_type["FP1"]["status"] == "loaded"
    assert by_type["Q"]["status"] == "loaded"
    assert by_type["R"]["status"] == "loaded"
    assert by_type["FP2"]["status"] is None
    assert by_type["FP3"]["status"] is None


def test_sessions_includes_date_utc(client, monkeypatch):
    from datetime import datetime

    from telogify.api import routes

    monkeypatch.setattr(
        routes,
        "session_schedule",
        lambda year, round: [("FP1", "Practice 1", datetime(2025, 6, 27, 11, 30))],
    )
    rows = client.get("/weekends/2025/11/sessions").json()
    assert rows == [{"session_type": "FP1", "status": "loaded", "date_utc": "2025-06-27T11:30:00Z"}]


def test_sessions_falls_back_to_ingested_when_schedule_unavailable(client, monkeypatch):
    from telogify.api import routes

    monkeypatch.setattr(routes, "session_schedule", lambda year, round: [])
    rows = client.get("/weekends/2025/11/sessions").json()
    assert [r["session_type"] for r in rows] == ["FP1", "Q", "R"]
    assert all(r["date_utc"] is None for r in rows)


def test_sessions_reports_unavailable_for_stale_never_ingested_session(client, monkeypatch):
    """A never-ingested session whose scheduled start + _STALE_AFTER has passed reads
    "unavailable" -- the server-derived cancellation-guard fallback."""
    from datetime import datetime, timedelta

    from telogify.api import routes
    from telogify.ingest.loader import _STALE_AFTER

    now = datetime.utcnow()
    monkeypatch.setattr(
        routes,
        "session_schedule",
        lambda year, round: [
            # FP2 is never ingested by the `client` fixture -- stale past its start + buffer.
            ("FP2", "Practice 2", now - _STALE_AFTER - timedelta(minutes=1)),
            # FP3 is also never ingested, but still inside the buffer -- stays null, not
            # "unavailable" (merely running late is not the same as stale/cancelled).
            ("FP3", "Practice 3", now - timedelta(minutes=1)),
            # FP1 IS ingested by the fixture (status "loaded") -- a stale date must never
            # override an already-`loaded` row.
            ("FP1", "Practice 1", now - _STALE_AFTER - timedelta(days=30)),
        ],
    )
    rows = client.get("/weekends/2025/11/sessions").json()
    by_type = {r["session_type"]: r for r in rows}
    assert by_type["FP2"]["status"] == "unavailable"
    assert by_type["FP3"]["status"] is None
    assert by_type["FP1"]["status"] == "loaded"


def test_sessions_returns_schedule_only_when_weekend_not_ingested(client, monkeypatch):
    """No RaceWeekend row exists yet for 2025/12 (the fixture only seeds 2025/11) -- this must
    render the calendar with every session unloaded, not 404 the way it did before the weekend
    row became optional."""
    from datetime import datetime

    from telogify.analysis.schedule import Event
    from telogify.api import routes

    # Round 12 is on the calendar (just not ingested) -- clears the "not ingested AND not on the
    # calendar either" 404 guard.
    monkeypatch.setattr(
        routes, "_schedule_events", lambda year: (Event(round=12, name="X", date=datetime(2099, 3, 1)),)
    )
    monkeypatch.setattr(
        routes,
        "session_schedule",
        lambda year, round: [("FP1", "Practice 1", datetime(2099, 3, 1, 10, 0))],
    )
    r = client.get("/weekends/2025/12/sessions")
    assert r.status_code == 200
    assert r.json() == [{"session_type": "FP1", "status": None, "date_utc": "2099-03-01T10:00:00Z"}]


def test_sessions_404_for_round_not_ingested_and_not_on_calendar(client, monkeypatch):
    """Unlike the case above, round 1 in the year 1999 isn't ingested AND isn't on the (here
    monkeypatched empty, so no live FastF1 call) calendar either -- this must 404 in agreement
    with weekend_detail, not silently answer "zero sessions" for a round that doesn't exist."""
    from telogify.api import routes

    monkeypatch.setattr(routes, "_schedule_events", lambda year: ())
    assert client.get("/weekends/1999/1/sessions").status_code == 404


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


def test_sectors_excludes_sprint_qualifying(client, test_engine):
    """SQ moved out of Practice's pooled sessions -- its sector bests must not appear here."""
    with Session(test_engine) as db:
        wk = db.exec(select(RaceWeekend).where(RaceWeekend.year == 2025, RaceWeekend.round == 11)).first()
        sq = SessionRow(weekend_id=wk.id, session_type="SQ", status="loaded")
        db.add(sq)
        db.commit()
        db.refresh(sq)
        db.add(SectorBest(session_id=sq.id, driver="VER", sector=1, best_time_s=1.0))
        db.commit()

    data = client.get("/weekends/2025/11/sectors").json()
    assert all(d["driver"] != "VER" for d in data["drivers"])
    assert "SQ" not in {d["session_type"] for d in data["drivers"]}


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


def test_latest_insight_none_when_no_insights_exist(test_engine):
    from telogify.api.main import app as fresh_app

    def override():
        with Session(test_engine) as s:
            yield s

    fresh_app.dependency_overrides[get_session] = override
    try:
        client = TestClient(fresh_app)
        assert client.get("/insights/latest").json() is None
    finally:
        fresh_app.dependency_overrides.clear()


def test_next_race_uses_schedule_events_cache_wrapper(client, monkeypatch):
    from datetime import datetime, timedelta

    from telogify.analysis.schedule import Event
    from telogify.api import routes

    routes._schedule_events.cache_clear()
    now = datetime.utcnow()
    events = (Event(round=9, name="Silverstone", date=now + timedelta(days=10)),)
    monkeypatch.setattr(routes, "fetch_season_schedule", lambda year: events if year == now.year else ())
    body = client.get("/next-race").json()
    assert body["event_name"] == "Silverstone"
    routes._schedule_events.cache_clear()


def test_next_race_none_when_no_upcoming_events(client, monkeypatch):
    from telogify.api import routes

    monkeypatch.setattr(routes, "_schedule_events", lambda year: ())
    assert client.get("/next-race").json() is None


def test_schedule_events_does_not_cache_a_transient_empty_fetch(monkeypatch):
    """A single failed/empty fetch_season_schedule call must not poison the cache for the rest
    of the process -- only a non-empty result is remembered, so the next call retries instead of
    permanently serving (). Both /season/{year}/weekends and the weekend_detail/sessions
    "coming soon" fallback depend on this to self-heal after a transient FastF1 outage."""
    from datetime import datetime

    from telogify.analysis.schedule import Event
    from telogify.api import routes

    routes._schedule_events.cache_clear()
    calls = {"n": 0}
    events = (Event(round=1, name="X", date=datetime.utcnow()),)

    def flaky(year):
        calls["n"] += 1
        return () if calls["n"] == 1 else events

    monkeypatch.setattr(routes, "fetch_season_schedule", flaky)
    assert routes._schedule_events(2030) == ()
    assert routes._schedule_events(2030) == events  # retried, not stuck on the empty result
    assert routes._schedule_events(2030) == events  # now cached for real
    assert calls["n"] == 2
    routes._schedule_events.cache_clear()


def test_empty_weekend_endpoints_return_placeholder_shapes(test_engine):
    """A weekend with no ingested sessions at all: every 'no data yet' branch in one pass."""
    with Session(test_engine) as db:
        wk = RaceWeekend(year=2024, round=1, circuit_name="X", country="Y", event_name="Empty GP")
        db.add(wk)
        db.commit()

    def override():
        with Session(test_engine) as s:
            yield s

    from telogify.api.main import app as fresh_app

    fresh_app.dependency_overrides[get_session] = override
    try:
        client = TestClient(fresh_app)
        assert client.get("/weekends/2024/1/pace").json()["drivers"] == []
        sectors = client.get("/weekends/2024/1/sectors").json()
        assert sectors == {"indicative": True, "drivers": [], "dominance": []}
        topspeeds = client.get("/weekends/2024/1/topspeeds").json()
        assert topspeeds == {"indicative": True, "drivers": []}
        qc = client.get("/weekends/2024/1/quali-character").json()
        assert qc["session_type"] is None and qc["rows"] == []
        trace = client.get("/weekends/2024/1/quali-trace").json()
        assert trace == {
            "session_type": None, "grid_m": [], "corners": [], "drivers": [],
            "pole_driver": None, "pole_lap_time_s": None,
        }
        degradation = client.get("/weekends/2024/1/degradation").json()
        assert degradation == {"fits": [], "points": [], "reference_age_laps": None}
        assert client.get("/weekends/2024/1/results").json() == []
        summary = client.get("/weekends/2024/1/session-summary?session=Q").json()
        assert summary["session_type"] is None and summary["order"] == []
    finally:
        fresh_app.dependency_overrides.clear()


def test_quali_trace_endpoint_serves_persisted_rows(test_engine):
    from telogify.models import QualiTrace

    with Session(test_engine) as db:
        wk = RaceWeekend(year=2023, round=1, circuit_name="X", country="Y", event_name="Trace GP")
        db.add(wk)
        db.commit()
        db.refresh(wk)
        quali = SessionRow(weekend_id=wk.id, session_type="Q", status="loaded")
        db.add(quali)
        db.commit()
        db.refresh(quali)
        db.add(QualiTrace(
            session_id=quali.id, driver="LEC", constructor="Ferrari", lap_time_s=80.0, is_pole=True,
            grid_m=[0.0, 100.0], corners_json=[{"number": 1, "distance_m": 50.0}],
            speed_kmh=[300.0, 310.0], throttle_pct=[100.0, 100.0], delta_s=[0.0, 0.0],
        ))
        db.commit()

    def override():
        with Session(test_engine) as s:
            yield s

    from telogify.api.main import app as fresh_app

    fresh_app.dependency_overrides[get_session] = override
    try:
        client = TestClient(fresh_app)
        out = client.get("/weekends/2023/1/quali-trace").json()
        assert out["session_type"] == "Q"
        assert out["drivers"][0]["driver"] == "LEC"
        assert out["drivers"][0]["is_pole"] is True
    finally:
        fresh_app.dependency_overrides.clear()


def _seed_quali_trace_weekend(test_engine, *, traces, results):
    """traces: list of (driver, constructor, lap_time_s, is_pole). results: list of
    (driver, position, q3_time_s). Returns nothing; use /weekends/2099/1/quali-trace."""
    from telogify.models import QualiTrace

    with Session(test_engine) as db:
        wk = RaceWeekend(year=2099, round=1, circuit_name="X", country="Y", event_name="Pole GP")
        db.add(wk)
        db.commit()
        db.refresh(wk)
        quali = SessionRow(weekend_id=wk.id, session_type="Q", status="loaded")
        db.add(quali)
        db.commit()
        db.refresh(quali)
        for drv, con, lt, is_pole in traces:
            db.add(QualiTrace(
                session_id=quali.id, driver=drv, constructor=con, lap_time_s=lt, is_pole=is_pole,
                grid_m=[0.0, 100.0], corners_json=[{"number": 1, "distance_m": 50.0}],
                speed_kmh=[300.0, 310.0], throttle_pct=[100.0, 100.0], delta_s=[0.0, 0.0],
            ))
        for drv, pos, q3 in results:
            db.add(SessionResult(session_id=quali.id, driver=drv, position=pos, q3_time_s=q3))
        db.commit()


def test_quali_trace_orders_by_official_classification_and_flags_official_pole(test_engine):
    # trace lap_time order (GAS fastest) matches official here; the point is is_pole comes from
    # SessionResult.position, and pole_driver/pole_lap_time_s are surfaced.
    _seed_quali_trace_weekend(
        test_engine,
        traces=[("RUS", "Mercedes", 81.846, False), ("GAS", "Alpine", 81.786, False), ("ANT", "Mercedes", 81.882, False)],
        results=[("GAS", 1, 81.786), ("RUS", 2, 81.846), ("ANT", 7, 81.882)],
    )

    def override():
        with Session(test_engine) as s:
            yield s

    from telogify.api.main import app as fresh_app

    fresh_app.dependency_overrides[get_session] = override
    try:
        out = TestClient(fresh_app).get("/weekends/2099/1/quali-trace").json()
        assert [d["driver"] for d in out["drivers"]] == ["GAS", "RUS", "ANT"]
        assert [d["is_pole"] for d in out["drivers"]] == [True, False, False]
        assert out["pole_driver"] == "GAS"
        assert out["pole_lap_time_s"] == 81.786
    finally:
        fresh_app.dependency_overrides.clear()


def test_quali_trace_flags_no_pole_when_official_pole_sitter_has_no_trace(test_engine):
    # 2026 R3 Japan shape: Antonelli took pole but his lap telemetry was scrubbed, so he has no
    # QualiTrace row. The chart must not call Russell pole -- no row is is_pole, but pole_driver
    # still names Antonelli so the frontend can relabel.
    _seed_quali_trace_weekend(
        test_engine,
        traces=[("RUS", "Mercedes", 89.076, True), ("PIA", "McLaren", 89.132, False)],
        results=[("ANT", 1, 88.778), ("RUS", 2, 89.076), ("PIA", 3, 89.132)],
    )

    def override():
        with Session(test_engine) as s:
            yield s

    from telogify.api.main import app as fresh_app

    fresh_app.dependency_overrides[get_session] = override
    try:
        out = TestClient(fresh_app).get("/weekends/2099/1/quali-trace").json()
        assert [d["driver"] for d in out["drivers"]] == ["RUS", "PIA"]
        assert not any(d["is_pole"] for d in out["drivers"])
        assert out["pole_driver"] == "ANT"
        assert out["pole_lap_time_s"] == 88.778
    finally:
        fresh_app.dependency_overrides.clear()


def test_degradation_skips_unmapped_constructor_and_missing_tyre_age(client, test_engine):
    with Session(test_engine) as db:
        wk = db.exec(select(RaceWeekend).where(RaceWeekend.year == 2025, RaceWeekend.round == 11)).first()
        race = db.exec(select(SessionRow).where(SessionRow.weekend_id == wk.id, SessionRow.session_type == "R")).first()
        # a driver with no SessionResult row -> no constructor mapping -> excluded
        db.add(Stint(
            session_id=race.id, driver="UNKNOWN", stint_number=1, compound="SOFT", lap_start=1, lap_end=6,
            avg_pace=90.0, lap_times_json=[90.0] * 6, tyre_ages_json=[1, 2, 3, 4, 5, 6],
        ))
        # a stint with a None tyre age entry -> that lap dropped
        db.add(Stint(
            session_id=race.id, driver="NOR", stint_number=2, compound="HARD", lap_start=21, lap_end=22,
            avg_pace=89.0, lap_times_json=[89.0, 89.5], tyre_ages_json=[None, 1],
        ))
        db.commit()

    data = client.get("/weekends/2025/11/degradation").json()
    assert not any(p["constructor"] == "UNKNOWN" for p in data["points"])
    assert not any(p["tyre_age"] is None for p in data["points"])


def test_session_summary_winner_total_time_takes_priority(client, test_engine):
    with Session(test_engine) as db:
        wk = db.exec(select(RaceWeekend).where(RaceWeekend.year == 2025, RaceWeekend.round == 11)).first()
        race = db.exec(select(SessionRow).where(SessionRow.weekend_id == wk.id, SessionRow.session_type == "R")).first()
        winner = db.exec(select(SessionResult).where(SessionResult.session_id == race.id, SessionResult.position == 1)).first()
        winner.total_time_s = 5432.106
        db.add(winner)
        db.commit()

    summary = client.get("/weekends/2025/11/session-summary?session=R").json()
    assert summary["order"][0]["gap_label"] == "1:30:32.106"


def test_results_winner_total_time_takes_priority_over_gap_label(client, test_engine):
    with Session(test_engine) as db:
        wk = db.exec(select(RaceWeekend).where(RaceWeekend.year == 2025, RaceWeekend.round == 11)).first()
        race = db.exec(select(SessionRow).where(SessionRow.weekend_id == wk.id, SessionRow.session_type == "R")).first()
        winner = db.exec(select(SessionResult).where(SessionResult.session_id == race.id, SessionResult.position == 1)).first()
        winner.total_time_s = 5432.106
        db.add(winner)
        db.commit()

    rows = client.get("/weekends/2025/11/results").json()
    assert rows[0]["gap_label"] == "1:30:32.106"


def test_season_snapshot_404_for_unseen_year(client):
    assert client.get("/season/2019").status_code == 404


def test_season_snapshot_ok_for_seeded_year(client):
    out = client.get("/season/2025").json()
    assert out["year"] == 2025
    assert "constructors" in out


def test_season_weekends_unions_ingested_and_schedule(client, monkeypatch):
    from datetime import datetime

    from telogify.analysis.schedule import Event
    from telogify.api import routes

    events = (
        # Round 11 is already ingested by the fixture (as "Austrian Grand Prix") -- the DB row's
        # fields must win over whatever the schedule says for it.
        Event(round=11, name="Schedule Name Ignored", date=datetime(2025, 6, 29), country="X", location="Y"),
        Event(round=12, name="Future GP", date=datetime(2025, 8, 1), country="Neverland", location="Nowhere City"),
    )
    monkeypatch.setattr(routes, "_schedule_events", lambda year: events if year == 2025 else ())

    rows = client.get("/season/2025/weekends").json()
    by_round = {r["round"]: r for r in rows}
    assert set(by_round) == {11, 12}

    assert by_round[11]["ingested"] is True
    assert by_round[11]["id"] is not None
    assert by_round[11]["event_name"] == "Austrian Grand Prix"
    assert by_round[11]["date_utc"] == "2025-06-29T00:00:00Z"

    assert by_round[12]["ingested"] is False
    assert by_round[12]["id"] is None
    assert by_round[12]["event_name"] == "Future GP"
    assert by_round[12]["circuit_name"] == "Nowhere City"
    assert by_round[12]["date_utc"] == "2025-08-01T00:00:00Z"


def test_season_weekends_degrades_to_ingested_only_when_schedule_unavailable(client, monkeypatch):
    from telogify.api import routes

    monkeypatch.setattr(routes, "_schedule_events", lambda year: ())
    rows = client.get("/season/2025/weekends").json()
    assert len(rows) == 1
    assert rows[0]["round"] == 11
    assert rows[0]["ingested"] is True
    assert rows[0]["date_utc"] is None


def test_quali_trace_endpoint_session_exists_without_rows(client):
    # fixture's Q session has no QualiTrace rows -> the "session exists but no traces" branch
    out = client.get("/weekends/2025/11/quali-trace").json()
    assert out == {
        "session_type": "Q", "grid_m": [], "corners": [], "drivers": [],
        "pole_driver": None, "pole_lap_time_s": None,
    }


def test_season_stats_404_for_unseen_year(client):
    assert client.get("/season/2019/stats").status_code == 404


def test_season_stats_ok_for_seeded_year(client):
    out = client.get("/season/2025/stats").json()
    assert out is not None and "total_laps" in out


def test_season_deployment_shape_without_insights(client):
    out = client.get("/season/2025/deployment").json()
    assert "scatter" in out and "pu_groups" in out and "insights" in out
    assert out["insights"] == []
    pu_names = {g["name"] for g in out["pu_groups"]}
    assert "Mercedes" in pu_names and "Ferrari" in pu_names


def test_season_deployment_serves_persisted_insights(client, test_engine):
    with Session(test_engine) as db:
        db.add(
            SeasonDeploymentInsight(
                year=2025, rank=1, pu_name="Ferrari", works_team="Ferrari",
                teams_json=["Ferrari", "Haas F1 Team"],
                header="Ferrari power holds acceleration best",
                explanation_web="Ferrari-powered cars kept accelerating hardest through the band.",
                source_metrics_json={"rank": 1, "pu": "Ferrari"},
            )
        )
        db.commit()
    out = client.get("/season/2025/deployment").json()
    assert len(out["insights"]) == 1
    row = out["insights"][0]
    assert row["slot"] == 1 and row["pu"] == "Ferrari" and row["works_team"] == "Ferrari"
    assert row["teams"] == ["Ferrari", "Haas F1 Team"]
    assert row["header"] == "Ferrari power holds acceleration best"


def test_subscribe_creates_one_pending_row_and_never_dedupes_aloud(client, test_engine):
    """Signup is double opt-in now, so the row starts `pending` and the response is the same
    whether or not the address was already known. The old test asserted the enumeration oracle
    (`subscribed` vs `already_subscribed`) that was deliberately removed. Full flow coverage,
    including verification and unsubscribe, lives in tests/test_subscribe_flow.py.
    """
    from sqlmodel import select

    from telogify.db import set_service_scope

    first = client.post("/subscribe", json={"email": "a@b.com"})
    second = client.post("/subscribe", json={"email": "a@b.com"})
    assert first.json() == second.json() == {"status": "check_your_inbox"}

    with Session(test_engine) as db:
        set_service_scope(db)
        subs = db.exec(select(Subscriber)).all()
    assert len(subs) == 1 and subs[0].status == "pending"


def test_chip_text_png_serves_valid_image(client):
    resp = client.get(
        "/chip/text.png",
        params={"text": "GEORGE RUSSELL", "font_size": 28, "text_color": "#27F4D2"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic bytes


def test_chip_text_png_with_background_serves_valid_image(client):
    resp = client.get(
        "/chip/text.png",
        params={
            "text": "Australian Grand Prix", "font_size": 15, "text_color": "#fff",
            "bg_color": "#E10600", "padding_top": 10, "padding_right": 18,
            "padding_bottom": 10, "padding_left": 18,
        },
    )
    assert resp.status_code == 200
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_chip_text_png_rejects_invalid_color(client):
    resp = client.get(
        "/chip/text.png",
        params={"text": "x", "font_size": 12, "text_color": "not-a-color"},
    )
    assert resp.status_code == 422


def test_production_origins_are_always_allowed_for_cors():
    """Regression: deriving the CORS allowlist from WEB_BASE_URL alone took the live site down.

    Railway had no WEB_BASE_URL set, because digests are sent from a developer machine whose
    .env does have one, so the allowlist collapsed to localhost and the deployed frontend was
    refused by every request it made. The site must not depend on an env var nobody knew was
    load-bearing.
    """
    from telogify.config import PRODUCTION_ORIGINS, Settings

    for web_base_url in ("http://localhost:5173", "https://example.invalid", ""):
        origins = Settings(web_base_url=web_base_url).cors_origins
        for production_origin in PRODUCTION_ORIGINS:
            assert production_origin in origins, (web_base_url, origins)


def test_cors_origin_regex_scopes_preview_deployments():
    """Vercel mints a new hostname per deployment, so previews cannot be listed ahead of time.

    The regex must stay project-scoped: a bare `.*\\.vercel\\.app` would let any site hosted on
    Vercel call this API. Unset by default, so production matches no wildcard at all.
    """
    import re

    from telogify.config import Settings

    assert Settings().cors_origin_regex == "", "previews must be opt-in"

    pattern = re.compile(r"https://telogify-[a-z0-9-]+\.vercel\.app")
    assert pattern.fullmatch("https://telogify-git-pre-prod-tanish.vercel.app")
    assert pattern.fullmatch("https://telogify-abc123.vercel.app")
    assert not pattern.fullmatch("https://evil.vercel.app")
    assert not pattern.fullmatch("https://telogify-x.vercel.app.evil.dev")
