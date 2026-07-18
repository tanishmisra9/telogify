import types
from datetime import datetime, timedelta

import fastf1
import pandas as pd
from sqlmodel import select

from telogify.ingest import loader
from telogify.models import RaceWeekend, Session

BASE = datetime(2026, 7, 18, 12, 0, 0)


def _dated_event(**sessions: str) -> pd.Series:
    """Build an event Series with Session{i}/Session{i}DateUtc pairs, each session an hour
    apart starting a day before BASE, in the given order."""
    fields: dict[str, object] = {}
    for i, (_, name) in enumerate(sessions.items(), start=1):
        fields[f"Session{i}"] = name
        fields[f"Session{i}DateUtc"] = BASE - timedelta(days=1) + timedelta(hours=i)
    return pd.Series(fields)


def test_list_weekend_sessions_sprint_format():
    event = pd.Series(
        {
            "Session1": "Practice 1",
            "Session2": "Sprint Qualifying",
            "Session3": "Sprint",
            "Session4": "Qualifying",
            "Session5": "Race",
        }
    )
    assert loader.list_weekend_sessions(event) == [
        ("FP1", "Practice 1"),
        ("SQ", "Sprint Qualifying"),
        ("SPRINT", "Sprint"),
        ("Q", "Qualifying"),
        ("R", "Race"),
    ]


def test_list_weekend_sessions_skips_empty():
    event = pd.Series(
        {"Session1": "Practice 1", "Session2": "", "Session3": float("nan"), "Session4": "Race"}
    )
    assert loader.list_weekend_sessions(event) == [("FP1", "Practice 1"), ("R", "Race")]


def test_completed_weekend_sessions_filters_future_sessions():
    event = _dated_event(
        s1="Practice 1", s2="Practice 2", s3="Practice 3", s4="Qualifying", s5="Race"
    )
    # Only the first two sessions (an hour and two hours before BASE - 1 day) have started;
    # bump `now` back to just after Practice 2 so Practice 3/Qualifying/Race are still future.
    now = BASE - timedelta(days=1) + timedelta(hours=2, minutes=30)
    assert loader.completed_weekend_sessions(event, now) == [
        ("FP1", "Practice 1"),
        ("FP2", "Practice 2"),
    ]


def test_completed_weekend_sessions_missing_date_excluded():
    event = pd.Series({"Session1": "Practice 1"})  # no date fields at all
    assert loader.completed_weekend_sessions(event, BASE) == []


def test_completed_weekend_sessions_skips_empty():
    event = _dated_event(s1="Practice 1", s2="Race")
    event["Session3"] = ""
    assert loader.completed_weekend_sessions(event, BASE) == [
        ("FP1", "Practice 1"),
        ("R", "Race"),
    ]


def test_weekend_session_dates_includes_future_sessions():
    # Unlike completed_weekend_sessions, nothing is filtered by date -- every calendar session
    # comes back, including ones scheduled well after `now` would be.
    event = _dated_event(s1="Practice 1", s2="Qualifying", s3="Race")
    dated = loader.weekend_session_dates(event)
    assert [(code, name) for code, name, _date in dated] == [
        ("FP1", "Practice 1"),
        ("Q", "Qualifying"),
        ("R", "Race"),
    ]
    assert all(date is not None for _code, _name, date in dated)


def test_weekend_session_dates_none_when_date_missing():
    event = pd.Series({"Session1": "Practice 1"})
    assert loader.weekend_session_dates(event) == [("FP1", "Practice 1", None)]


def test_session_schedule_returns_empty_on_fastf1_failure(monkeypatch):
    monkeypatch.setattr("telogify.ingest.fastf1_cache.enable_cache", lambda: None)

    def _boom(y, r):
        raise RuntimeError("no network")

    monkeypatch.setattr(fastf1, "get_event", _boom)
    assert loader.session_schedule(2025, 11) == []


def test_session_schedule_delegates_to_weekend_session_dates(monkeypatch):
    event = _dated_event(s1="Practice 1", s2="Race")
    monkeypatch.setattr("telogify.ingest.fastf1_cache.enable_cache", lambda: None)
    monkeypatch.setattr(fastf1, "get_event", lambda y, r: event)

    assert loader.session_schedule(2025, 11) == loader.weekend_session_dates(event)


def test_load_weekend_persists(db_session, monkeypatch):
    event = _dated_event(
        s1="Practice 1", s2="Practice 2", s3="Practice 3", s4="Qualifying", s5="Race"
    )
    event["EventName"] = "Austrian Grand Prix"
    event["Country"] = "Austria"
    event["Location"] = "Spielberg"
    monkeypatch.setattr("telogify.ingest.fastf1_cache.enable_cache", lambda: None)
    monkeypatch.setattr(fastf1, "get_event", lambda y, r: event)
    monkeypatch.setattr(
        fastf1, "get_session", lambda y, r, name: types.SimpleNamespace(load=lambda *a, **k: None)
    )

    data = loader.load_weekend(2025, 11, db_session, now=BASE)

    weekends = db_session.exec(select(RaceWeekend)).all()
    assert len(weekends) == 1
    assert weekends[0].circuit_name == "Spielberg"
    assert weekends[0].event_name == "Austrian Grand Prix"

    types_present = {s.session_type for s in db_session.exec(select(Session)).all()}
    assert types_present == {"FP1", "FP2", "FP3", "Q", "R"}
    assert set(data.sessions) == types_present


def test_load_weekend_only_ingests_completed_sessions(db_session, monkeypatch):
    event = _dated_event(
        s1="Practice 1", s2="Practice 2", s3="Practice 3", s4="Qualifying", s5="Race"
    )
    event["EventName"] = "Austrian Grand Prix"
    event["Country"] = "Austria"
    event["Location"] = "Spielberg"
    monkeypatch.setattr("telogify.ingest.fastf1_cache.enable_cache", lambda: None)
    monkeypatch.setattr(fastf1, "get_event", lambda y, r: event)
    monkeypatch.setattr(
        fastf1, "get_session", lambda y, r, name: types.SimpleNamespace(load=lambda *a, **k: None)
    )

    # Only Practice 1/2 have started as of this `now`; Practice 3, Qualifying, and Race haven't.
    now = BASE - timedelta(days=1) + timedelta(hours=2, minutes=30)
    data = loader.load_weekend(2025, 11, db_session, now=now)

    types_present = {s.session_type for s in db_session.exec(select(Session)).all()}
    assert types_present == {"FP1", "FP2"}
    assert set(data.sessions) == {"FP1", "FP2"}
