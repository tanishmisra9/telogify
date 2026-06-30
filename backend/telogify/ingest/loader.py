"""Load every session present on a race weekend via FastF1, persist weekend + session rows.

The FastF1-touching code is kept thin so the session enumeration and persistence
logic can be tested offline (see tests/test_loader.py).
"""

import os
from dataclasses import dataclass, field

import fastf1
import pandas as pd
from sqlmodel import Session as DBSession
from sqlmodel import select

from telogify.config import settings
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

_cache_enabled = False


@dataclass
class WeekendData:
    weekend: RaceWeekend
    sessions: dict[str, "fastf1.core.Session"] = field(default_factory=dict)


def _enable_cache() -> None:
    global _cache_enabled
    if not _cache_enabled:
        os.makedirs(settings.fastf1_cache, exist_ok=True)
        fastf1.Cache.enable_cache(settings.fastf1_cache)
        _cache_enabled = True


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


def load_weekend(year: int, round: int, db: DBSession) -> WeekendData:
    """Load all present sessions for (year, round), persist weekend + session rows."""
    _enable_cache()
    event = fastf1.get_event(year, round)
    weekend = _upsert_weekend(db, year, round, event)

    sessions: dict[str, fastf1.core.Session] = {}
    for code, name in list_weekend_sessions(event):
        ses = fastf1.get_session(year, round, name)
        ses.load()
        _upsert_session(db, weekend.id, code, status="loaded")
        sessions[code] = ses
    db.commit()
    return WeekendData(weekend=weekend, sessions=sessions)
