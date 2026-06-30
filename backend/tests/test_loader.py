import types

import fastf1
import pandas as pd
from sqlmodel import select

from telogify.ingest import loader
from telogify.models import RaceWeekend, Session


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


def test_load_weekend_persists(db_session, monkeypatch):
    event = pd.Series(
        {
            "Session1": "Practice 1",
            "Session2": "Practice 2",
            "Session3": "Practice 3",
            "Session4": "Qualifying",
            "Session5": "Race",
            "EventName": "Austrian Grand Prix",
            "Country": "Austria",
            "Location": "Spielberg",
        }
    )
    monkeypatch.setattr(loader, "_enable_cache", lambda: None)
    monkeypatch.setattr(fastf1, "get_event", lambda y, r: event)
    monkeypatch.setattr(
        fastf1, "get_session", lambda y, r, name: types.SimpleNamespace(load=lambda *a, **k: None)
    )

    data = loader.load_weekend(2025, 11, db_session)

    weekends = db_session.exec(select(RaceWeekend)).all()
    assert len(weekends) == 1
    assert weekends[0].circuit_name == "Spielberg"
    assert weekends[0].event_name == "Austrian Grand Prix"

    types_present = {s.session_type for s in db_session.exec(select(Session)).all()}
    assert types_present == {"FP1", "FP2", "FP3", "Q", "R"}
    assert set(data.sessions) == types_present
