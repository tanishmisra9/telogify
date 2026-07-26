"""Load every session present on a race weekend via FastF1, persist weekend + session rows.

The FastF1-touching code is kept thin so the session enumeration and persistence
logic can be tested offline (see tests/test_loader.py).
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

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

# Tuning knob: how long a session runs, used to derive a scheduled end since FastF1's schedule
# exposes only start times. Practice/quali ~1h; sprint sessions ~45min; race ~2h.
_NOMINAL_DURATION: dict[str, timedelta] = {
    "FP1": timedelta(hours=1),
    "FP2": timedelta(hours=1),
    "FP3": timedelta(hours=1),
    "Q": timedelta(hours=1),
    "SQ": timedelta(minutes=45),
    "SPRINT": timedelta(minutes=45),
    "R": timedelta(hours=2),
}
_DEFAULT_DURATION = timedelta(hours=1)  # fallback for an unmapped/unknown code

# Tuning knob: how long after a session *ends* before FastF1's data is reliably complete.
_DATA_LAG = timedelta(hours=1)

# Tuning knob: minimum distinct drivers in a completeness probe. Set low so a legitimately
# washed-out session still clears it -- a false negative here means the session never
# auto-ingests, which is worse than a marginal false positive.
_MIN_DRIVERS = 5

# How far past a session's scheduled START it's treated as stale/cancelled rather than merely
# running late. Shared by the poll command's round window and the API's cancellation-guard
# fallback (both compare against scheduled start, not the derived-ready time above -- a
# session can be "stale" long before it would ever have been eligible to ingest).
_STALE_AFTER = timedelta(hours=6)


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
    """Sessions on this weekend whose scheduled end plus a data-availability lag has passed by
    `now` -- i.e. sessions that have actually finished and whose FastF1 data should be reliably
    complete, not just sessions that have started. FastF1's schedule has no end times, so the
    end is derived from the scheduled start plus a per-type nominal duration
    (`_NOMINAL_DURATION`) plus `_DATA_LAG`. A session with no date info at all is excluded
    (unknown -> treat as not-yet-run)."""
    out: list[tuple[str, str]] = []
    for i in range(1, 6):
        name = event.get(f"Session{i}")
        if name is None or (isinstance(name, float) and pd.isna(name)) or name == "":
            continue
        code = _NAME_TO_TYPE.get(name)
        if not code:
            continue
        date = _session_date(event, i)
        if date is None:
            continue
        ready_at = date + _NOMINAL_DURATION.get(code, _DEFAULT_DURATION) + _DATA_LAG
        if ready_at <= now:
            out.append((code, name))
    return out


def _has_usable_data(ses: "fastf1.core.Session") -> bool:
    """Whether a loaded session actually has data, as opposed to a soft-failed `.load()` that
    returned normally with nothing loaded (FastF1 wraps its internal loaders in
    `@soft_exceptions`, which swallows `NoLapDataError`/`SessionNotAvailableError` into log
    warnings rather than raising). Probes laps AND telemetry independently: `_load_laps_data`
    and `_load_telemetry` are soft-wrapped separately, so laps can load fine while telemetry
    silently fails -- and telemetry is what several of the product's insights (ERS deployment,
    straight-line speed, sector dominance) actually depend on."""
    try:
        laps = ses.laps
    except Exception:
        return False
    if laps is None or laps.empty or laps["DriverNumber"].nunique() < _MIN_DRIVERS:
        return False
    try:
        car_data = ses.car_data
    except Exception:
        return False
    return bool(car_data)


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


def _existing_session_types(db: DBSession, weekend_id: int) -> set[str]:
    rows = db.exec(select(Session).where(Session.weekend_id == weekend_id)).all()
    return {r.session_type for r in rows}


def load_weekend(
    year: int, round: int, db: DBSession, now: datetime | None = None, force: bool = False
) -> WeekendData:
    """Load every session ready for (year, round) (scheduled end + data lag has passed),
    persist weekend + session rows. A session not yet ready (mid-weekend, e.g. only practice
    has happened) is simply skipped, so this is safe to call at any point during a race weekend
    -- including from an unattended recurring poll.

    A session already ingested by a prior call is skipped too (no re-fetch, no re-run of the
    extractors) unless `force`, so re-running this on a recurring schedule (e.g. a cron) doesn't
    redo already-done work every tick. Safe because every ingest extractor deletes-and-reinserts
    scoped to the session_ids present in the returned WeekendData.sessions, not the whole
    weekend -- a skipped session's existing rows are simply never touched, not left stale.

    A session whose `.load()` soft-failed (see `_has_usable_data`) is left un-ingested rather
    than marked `loaded`, so the next call retries it -- unless `force`, which is the manual
    escape hatch for a session whose data genuinely never becomes complete (e.g. no telemetry
    ever published), since an automated poll must never write `loaded` for a soft-failed load."""
    enable_cache()
    event = fastf1.get_event(year, round)
    weekend = _upsert_weekend(db, year, round, event)
    already = set() if force else _existing_session_types(db, weekend.id)

    sessions: dict[str, fastf1.core.Session] = {}
    for code, name in completed_weekend_sessions(event, now or datetime.utcnow()):
        if code in already:
            continue
        ses = fastf1.get_session(year, round, name)
        ses.load()
        if not force and not _has_usable_data(ses):
            continue
        _upsert_session(db, weekend.id, code, status="loaded")
        sessions[code] = ses
    db.commit()
    return WeekendData(weekend=weekend, sessions=sessions)
