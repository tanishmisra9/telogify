"""Load every session present on a race weekend via FastF1, persist weekend + session rows.

The FastF1-touching code is kept thin so the session enumeration and persistence
logic can be tested offline (see tests/test_loader.py).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import fastf1
import pandas as pd
from sqlmodel import Session as DBSession
from sqlmodel import select

from telogify.ingest import openf1
from telogify.ingest.fastf1_cache import enable_cache
from telogify.models import RaceWeekend, Session

logger = logging.getLogger("telogify.ingest")

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

# A load whose fastest car never exceeds this is stationary junk, not telemetry (FastF1 3.9.1
# decoded Mexico's race to cars sitting at 0 km/h). Far below any real session's top speed.
_MIN_TOP_SPEED_KMH = 50.0

# How many laps shorter than the classified race the lap table may be before the load is treated
# as truncated (FastF1's Mexico 2026 race feed stopped at lap 56 of 71). Every 2026 race ingested so
# far matches exactly; the slack only absorbs a missing final-lap record.
_MAX_MISSING_LAPS = 2

# How far past a session's scheduled START it's treated as stale/cancelled rather than merely
# running late. Shared by the poll command's round window and the API's cancellation-guard
# fallback (both compare against scheduled start, not the derived-ready time above -- a
# session can be "stale" long before it would ever have been eligible to ingest).
_STALE_AFTER = timedelta(hours=6)

# How far back the poll command still revisits a round (by scheduled race start). Wider than
# _STALE_AFTER on purpose: a race becomes eligible 3h after it starts, and if FastF1's results
# are still incomplete then (see `_results_ready`) the poll must keep retrying for hours, not for
# the ~3h the 6h window would leave. Kept separate because _STALE_AFTER also drives the API's
# "stale session" status.
_POLL_LOOKBACK = timedelta(hours=24)


@dataclass
class WeekendData:
    weekend: RaceWeekend
    sessions: dict[str, "fastf1.core.Session"] = field(default_factory=dict)
    # Session codes finished but deliberately NOT ingested this call because FastF1's results
    # were incomplete (see `_results_ready`); surfaced so a manual run can say so.
    held_back: list[str] = field(default_factory=list)


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
    if not car_data:
        return False
    try:
        top_speed = max(float(tel["Speed"].max()) for tel in car_data.values())
    except Exception:
        return False
    if not top_speed > _MIN_TOP_SPEED_KMH:
        logger.warning("telemetry never moves (top speed %s km/h)", top_speed)
        return False
    return not _laps_truncated(ses)


def _laps_truncated(ses: "fastf1.core.Session") -> bool:
    """Whether a race-like session's lap table stops short of the classified race, e.g. a feed cut
    off mid-race. Without this, such a load is stored as a shorter race: wrong total laps (fuel
    correction), missing laps in every stint, and insights about a race that did not happen.
    Judged against the leader's classified laps from `results`; unreadable results mean "cannot
    tell", which the results gate already handles."""
    from telogify.ingest.results import requires_complete_results

    if not requires_complete_results(getattr(ses, "name", "") or ""):
        return False
    try:
        res = ses.results
        classified = float(res[res["Position"] == 1].iloc[0]["Laps"])
        longest = float(ses.laps["LapNumber"].max())
    except Exception:
        return False
    if pd.isna(classified) or pd.isna(longest):
        return False
    if classified - longest > _MAX_MISSING_LAPS:
        logger.warning(
            "lap data truncated: laps end at %d of %d classified", int(longest), int(classified)
        )
        return True
    return False


def _has_complete_results(ses: "fastf1.core.Session") -> bool:
    """Whether a loaded race-like session's `results` is the complete table (see
    `results.race_results_complete`), not FastF1's silently degraded driver-info-only fallback.
    `_has_usable_data` never looks at results, which is how a position-only table got stored as
    `loaded` and then skipped forever. Imported lazily: results.py imports WeekendData from here."""
    from telogify.ingest.results import race_results_complete

    try:
        return race_results_complete(ses.results)
    except Exception as exc:
        # Logged, not just swallowed: a parsing bug here would otherwise look identical to
        # genuinely incomplete results and silently hold every race back.
        logger.warning("results unreadable (%s: %s)", type(exc).__name__, exc)
        return False


def _results_ready(year: int, round: int, name: str) -> bool:
    """Cheap pre-check before the full (laps + telemetry) load: probe only the results. A race
    whose results are still lagging would otherwise cost a full cold load on every poll tick
    (minutes each, with no cache volume on Railway) just to be discarded afterwards."""
    try:
        probe = fastf1.get_session(year, round, name)
        probe.load(laps=False, telemetry=False, weather=False, messages=False)
    except Exception as exc:
        logger.warning("%s %s %s: results probe failed (%s)", year, round, name, exc)
        return False
    return _has_complete_results(probe)


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


def _load_fastf1(
    year: int, round: int, name: str, gated: bool, force: bool, swallow_errors: bool
) -> tuple["fastf1.core.Session | None", str]:
    """FastF1 load + the usable/complete gates. Returns (session, "ok") or (None, why) where why is
    "unusable" (skip, retry next tick) or "held_back" (results incomplete). An exception from
    FastF1 propagates -- the cron run should fail visibly -- unless `swallow_errors`, i.e. a
    fallback exists to take over."""
    try:
        ses = fastf1.get_session(year, round, name)
        ses.load()
    except Exception as exc:
        if not swallow_errors:
            raise
        logger.warning("%s round %s %s: FastF1 load failed (%s: %s)", year, round, name, type(exc).__name__, exc)
        return None, "unusable"
    if not force and not _has_usable_data(ses):
        return None, "unusable"
    if gated and not _has_complete_results(ses):
        return None, "held_back"
    return ses, "ok"


def _load_openf1(
    year: int, round: int, name: str, start: datetime, gated: bool, fastf1_outcome: str
) -> tuple["fastf1.core.Session | None", str]:
    """OpenF1 rebuild held to the same gates as a FastF1 load. Any failure is logged and leaves
    the session un-ingested for the next tick, with the FastF1 outcome kept for the caller."""
    logger.warning("%s round %s %s: FastF1 unusable, falling back to OpenF1", year, round, name)
    try:
        ses = openf1.load_session(year, round, name, start)
    except Exception as exc:
        logger.warning("%s round %s %s: OpenF1 fallback failed (%s: %s)", year, round, name, type(exc).__name__, exc)
        return None, fastf1_outcome
    if not _has_usable_data(ses):
        return None, "unusable"
    if gated and not _has_complete_results(ses):
        return None, "held_back"
    logger.warning("%s round %s %s: ingested from OpenF1", year, round, name)
    return ses, "ok"


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
    ever published), since an automated poll must never write `loaded` for a soft-failed load.

    A race-like session is held back the same way until FastF1's results table is complete
    (`_has_complete_results`): storing the degraded position-only table would also trigger
    insight generation and the real digest from wrong finishing positions. `force` bypasses this
    gate too."""
    from telogify.ingest.results import requires_complete_results

    enable_cache()
    event = fastf1.get_event(year, round)
    weekend = _upsert_weekend(db, year, round, event)
    already = set() if force else _existing_session_types(db, weekend.id)

    sessions: dict[str, fastf1.core.Session] = {}
    held_back: list[str] = []
    now = now or datetime.utcnow()
    starts = {code: start for code, _, start in weekend_session_dates(event)}
    for code, name in completed_weekend_sessions(event, now):
        if code in already:
            continue
        start = starts.get(code)
        # OpenF1 steps in only for a session that started long enough ago that FastF1 not
        # having it is a failure, not lag: an ingested session is never re-fetched, so falling
        # back early could lock in coarser data FastF1 would have had an hour later.
        may_fall_back = openf1.enabled() and start is not None and now - start > _STALE_AFTER
        gated = not force and requires_complete_results(name)

        ses, outcome = None, "held_back"
        if not gated or _results_ready(year, round, name):
            ses, outcome = _load_fastf1(year, round, name, gated, force, may_fall_back)
        if ses is None and may_fall_back:
            ses, outcome = _load_openf1(year, round, name, start, gated, outcome)
        if ses is None:
            if outcome == "held_back":
                logger.warning("%s round %s %s: results incomplete, will retry next poll", year, round, name)
                held_back.append(code)
            continue
        _upsert_session(db, weekend.id, code, status="loaded")
        sessions[code] = ses
    db.commit()
    return WeekendData(weekend=weekend, sessions=sessions, held_back=held_back)


def load_race_for_backfill(year: int, round: int, now: datetime | None = None) -> "fastf1.core.Session | None":
    """Just the Race session's laps + telemetry, through the same FastF1-then-OpenF1 path and
    usable-data gates as `load_weekend`, with no DB writes and no other session loaded. For
    repairing one table on an already-ingested round (see pipeline.run_refresh_race_start).
    None when the race has not happened or neither source has usable data."""
    enable_cache()
    event = fastf1.get_event(year, round)
    now = now or datetime.utcnow()
    names = dict(list_weekend_sessions(event))
    start = {code: s for code, _, s in weekend_session_dates(event)}.get("R")
    if "R" not in names or "R" not in {c for c, _ in completed_weekend_sessions(event, now)}:
        return None
    may_fall_back = openf1.enabled() and start is not None and now - start > _STALE_AFTER
    ses, outcome = _load_fastf1(year, round, names["R"], gated=False, force=False, swallow_errors=may_fall_back)
    if ses is None and may_fall_back:
        ses, outcome = _load_openf1(year, round, names["R"], start, gated=False, fastf1_outcome=outcome)
    return ses
