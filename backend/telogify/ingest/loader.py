"""Load every session present on a race weekend via FastF1, persist weekend + session rows.

The FastF1-touching code is kept thin so the session enumeration and persistence
logic can be tested offline (see tests/test_loader.py).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

import fastf1
import pandas as pd
from sqlmodel import Session as DBSession
from sqlmodel import select

from telogify.ingest.fastf1_cache import enable_cache
from telogify.models import RaceWeekend, Session

# FastF1 full session name -> our session_type code.
_NAME_TO_TYPE = {
    "Practice 1": "FP1",
    "Practice 2": "FP2",
    "Practice 3": "FP3",
    "Qualifying": "Q",
    "Sprint Qualifying": "SQ",
    "Sprint Shootout": "SQ",
    "Sprint": "SPRINT",
    "Race": "R",
}


@dataclass
class WeekendData:
    weekend: RaceWeekend
    sessions: dict[str, "fastf1.core.Session"] = field(default_factory=dict)


def list_weekend_sessions(event: pd.Series) -> list[tuple[str, str]]:
    """Return [(session_type_code, fastf1_name)] for sessions present on the event, in order."""
    out: list[tuple[str, str]] = []
    for i in range(1, 6):
        name = event.get(f"Session{i}")
        if name is None or (isinstance(name, float) and pd.isna(name)) or name == "":
            continue
        code = _NAME_TO_TYPE.get(name)
        if code:
            out.append((code, name))
    return out


def _session_date(event: pd.Series, i: int) -> datetime | None:
    raw = event.get(f"Session{i}DateUtc")
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        raw = event.get(f"Session{i}Date")
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    dt = pd.Timestamp(raw).to_pydatetime()
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def weekend_session_dates(event: pd.Series) -> list[tuple[str, str, datetime | None]]:
    """Every session on this weekend's calendar, in order, each tagged with its scheduled start
    (None if the schedule has no date for it). Unlike completed_weekend_sessions, this doesn't
    filter by date -- it's for surfacing a countdown to sessions that haven't started yet."""
    out: list[tuple[str, str, datetime | None]] = []
    for i in range(1, 6):
        name = event.get(f"Session{i}")
        if name is None or (isinstance(name, float) and pd.isna(name)) or name == "":
            continue
        code = _NAME_TO_TYPE.get(name)
        if not code:
            continue
        out.append((code, name, _session_date(event, i)))
    return out


def session_schedule(year: int, round: int) -> list[tuple[str, str, datetime | None]]:
    """FastF1's per-session schedule for one weekend (live network call, FastF1-cached).
    Returns [] if the schedule can't be fetched (offline, unknown round, etc.)."""
    try:
        enable_cache()
        event = fastf1.get_event(year, round)
    except Exception:
        return []
    return weekend_session_dates(event)


def completed_weekend_sessions(event: pd.Series, now: datetime) -> list[tuple[str, str]]:
    """Sessions on this weekend whose scheduled start is on or before `now` -- i.e. sessions
    that have actually started, not just sessions listed on the calendar. A session with no
    date info at all is excluded (unknown -> treat as not-yet-run)."""
    out: list[tuple[str, str]] = []
    for i in range(1, 6):
        name = event.get(f"Session{i}")
        if name is None or (isinstance(name, float) and pd.isna(name)) or name == "":
            continue
        code = _NAME_TO_TYPE.get(name)
        if not code:
            continue
        date = _session_date(event, i)
        if date is not None and date <= now:
            out.append((code, name))
    return out


def _upsert_weekend(db: DBSession, year: int, round: int, event: pd.Series) -> RaceWeekend:
    weekend = db.exec(
        select(RaceWeekend).where(RaceWeekend.year == year, RaceWeekend.round == round)
    ).first()
    if weekend is None:
        weekend = RaceWeekend(year=year, round=round, circuit_name="", country="", event_name="")
        db.add(weekend)
    weekend.circuit_name = str(event.get("Location") or "")
    weekend.country = str(event.get("Country") or "")
    weekend.event_name = str(event.get("EventName") or "")
    db.add(weekend)
    db.commit()
    db.refresh(weekend)
    return weekend


def _upsert_session(db: DBSession, weekend_id: int, code: str, status: str) -> None:
    row = db.exec(
        select(Session).where(Session.weekend_id == weekend_id, Session.session_type == code)
    ).first()
    if row is None:
        row = Session(weekend_id=weekend_id, session_type=code, status=status)
    else:
        row.status = status
    db.add(row)


def load_weekend(year: int, round: int, db: DBSession, now: datetime | None = None) -> WeekendData:
    """Load every session that has started for (year, round), persist weekend + session rows.
    A session not yet run (mid-weekend, e.g. only practice has happened) is simply skipped, so
    this is safe to call at any point during a race weekend."""
    enable_cache()
    event = fastf1.get_event(year, round)
    weekend = _upsert_weekend(db, year, round, event)

    sessions: dict[str, fastf1.core.Session] = {}
    for code, name in completed_weekend_sessions(event, now or datetime.utcnow()):
        ses = fastf1.get_session(year, round, name)
        ses.load()
        _upsert_session(db, weekend.id, code, status="loaded")
        sessions[code] = ses
    db.commit()
    return WeekendData(weekend=weekend, sessions=sessions)
