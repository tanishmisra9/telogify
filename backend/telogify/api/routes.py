"""Read endpoints for the weekend page (insights, pace, sectors, top speeds, qualifying
car character, tyre degradation, finishing order, session progress), plus subscribe."""

from datetime import datetime, timezone
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from telogify.analysis.schedule import Event, pick_next_event

from telogify.analysis.attribution import _driver_constructor_map
from telogify.analysis.degradation import REFERENCE_AGE_LAPS, fit_all_groups
from telogify.analysis.quali_character import (
    fastest_qualifier_per_constructor,
    label_car_character,
    pick_fastest_corner,
)
from telogify.analysis.race_pace import (
    constructor_distributions,
    driver_distributions,
    driver_stop_counts,
    stop_count_spread,
)
from telogify.analysis.sectors import best_across_sessions, best_top_speeds, sector_dominance
from telogify.analysis.season import build_season_snapshot
from telogify.ingest.results import (
    format_gap_label,
    format_total_time,
    points_for_session,
    strategy_string,
)
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

router = APIRouter()

# Chronological order for a weekend page. Sprint weekends insert SQ/SPRINT before Q;
# sessions absent from a weekend are simply skipped, never shown as blanks or errors.
SESSION_ORDER = ["FP1", "FP2", "FP3", "SQ", "SPRINT", "Q", "R"]
PRACTICE_SESSIONS = ("FP1", "FP2", "FP3")
# Car character compares the front of the field, not the whole grid: "leader" labels
# (best top speed, best downforce, ...) are computed relative to this set, so trimming
# happens before labeling, not after.
TOP_TEAMS_N = 5


class SubscribeIn(BaseModel):
    email: str
    followed_constructor: str | None = None


def _weekend(db: Session, year: int, round: int) -> RaceWeekend:
    w = db.exec(
        select(RaceWeekend).where(RaceWeekend.year == year, RaceWeekend.round == round)
    ).first()
    if w is None:
        raise HTTPException(status_code=404, detail="weekend not found")
    return w


def _session_of(db: Session, weekend_id: int, session_type: str) -> SessionRow | None:
    return db.exec(
        select(SessionRow).where(
            SessionRow.weekend_id == weekend_id, SessionRow.session_type == session_type
        )
    ).first()


def _race_session(db: Session, weekend_id: int) -> SessionRow | None:
    """Sunday race session (explicit R, not sprint)."""
    return _session_of(db, weekend_id, "R")


def _driver_constructor(db: Session, session_id: int) -> dict[str, str]:
    rows = db.exec(select(SessionResult).where(SessionResult.session_id == session_id)).all()
    return {r.driver: r.constructor for r in rows if r.constructor}


def _weekend_sessions(db: Session, weekend_id: int) -> list[SessionRow]:
    rows = db.exec(select(SessionRow).where(SessionRow.weekend_id == weekend_id)).all()
    return sorted(rows, key=lambda r: SESSION_ORDER.index(r.session_type) if r.session_type in SESSION_ORDER else 99)


def _weekend_driver_constructor(db: Session, weekend_id: int) -> dict[str, str]:
    session_ids = [s.id for s in _weekend_sessions(db, weekend_id)]
    return _driver_constructor_map(db, session_ids)


def _session_by_type(sessions: list[SessionRow], session_type: str) -> SessionRow | None:
    return next((s for s in sessions if s.session_type == session_type), None)


@router.get("/weekends")
def list_weekends(db: Session = Depends(get_session)):
    rows = db.exec(
        select(RaceWeekend).order_by(RaceWeekend.year.asc(), RaceWeekend.round.asc())
    ).all()
    return [
        {
            "id": w.id,
            "year": w.year,
            "round": w.round,
            "event_name": w.event_name,
            "circuit_name": w.circuit_name,
            "country": w.country,
        }
        for w in rows
    ]


@router.get("/insights/latest")
def latest_insight(db: Session = Depends(get_session)):
    """Strongest insight (slot 1) of the most recent analysed weekend, for the landing page.
    Returns null when no insights have been published yet."""
    row = db.exec(
        select(Insight, RaceWeekend)
        .join(RaceWeekend, Insight.weekend_id == RaceWeekend.id)
        .order_by(RaceWeekend.year.desc(), RaceWeekend.round.desc(), Insight.slot.asc())
    ).first()
    if row is None:
        return None
    ins, w = row
    return {
        "slot": ins.slot,
        "header": ins.header,
        "explanation_web": ins.explanation_web,
        "year": w.year,
        "round": w.round,
        "event_name": w.event_name,
    }


@lru_cache(maxsize=4)
def _schedule_events(year: int) -> tuple[Event, ...]:
    """FastF1 season schedule mapped to Event rows (naive UTC dates). Cached per season;
    returns () on any failure so the endpoint degrades to 'no countdown'. The pick of which
    event is next is computed per-request against the current time, so caching the (stable)
    schedule here is safe."""
    try:
        import fastf1
        import pandas as pd

        sched = fastf1.get_event_schedule(year, include_testing=False)
    except Exception:
        return ()

    events: list[Event] = []
    for _, r in sched.iterrows():
        # Prefer the race-session start; fall back to the event date.
        raw = r.get("Session5DateUtc")
        if raw is None or pd.isna(raw):
            raw = r.get("Session5Date")
        if raw is None or pd.isna(raw):
            raw = r.get("EventDate")
        if raw is None or pd.isna(raw):
            continue
        dt = pd.Timestamp(raw).to_pydatetime()
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        events.append(
            Event(round=int(r.get("RoundNumber") or 0), name=str(r.get("EventName") or ""), date=dt)
        )
    return tuple(events)


@router.get("/next-race")
def next_race():
    """Next upcoming F1 event for the landing-page countdown. Reads FastF1's schedule live
    (disk-cached by FastF1, and per-season in-process). Returns null when the season is over
    and next year's schedule isn't out, or when FastF1 is unavailable, so the frontend simply
    hides the countdown."""
    now = datetime.utcnow()
    ev = pick_next_event(list(_schedule_events(now.year)), now)
    if ev is None:
        ev = pick_next_event(list(_schedule_events(now.year + 1)), now)
    if ev is None:
        return None
    return {"event_name": ev.name, "round": ev.round, "date_utc": ev.date.isoformat() + "Z"}


@router.get("/weekends/{year}/{round}")
def weekend_detail(year: int, round: int, db: Session = Depends(get_session)):
    w = _weekend(db, year, round)
    return {
        "id": w.id,
        "year": w.year,
        "round": w.round,
        "event_name": w.event_name,
        "circuit_name": w.circuit_name,
        "country": w.country,
    }


@router.get("/weekends/{year}/{round}/sessions")
def weekend_sessions(year: int, round: int, db: Session = Depends(get_session)):
    """Which sessions of this weekend have been ingested, in chronological order. The
    frontend renders a section per session present here; a session simply not in this
    list (not yet run, or a standard weekend with no SQ/SPRINT) renders as 'upcoming'."""
    w = _weekend(db, year, round)
    sessions = _weekend_sessions(db, w.id)
    return [{"session_type": s.session_type, "status": s.status} for s in sessions]


@router.get("/weekends/{year}/{round}/insights")
def weekend_insights(year: int, round: int, db: Session = Depends(get_session)):
    w = _weekend(db, year, round)
    rows = db.exec(
        select(Insight).where(Insight.weekend_id == w.id).order_by(Insight.slot)
    ).all()
    return [
        {"slot": r.slot, "header": r.header, "explanation_web": r.explanation_web} for r in rows
    ]


def _pace_row_to_dict(row) -> dict:
    s = row.stats
    return {
        "id": row.id,
        "label": row.label,
        "team": row.team,
        "gap_to_fastest_s": row.gap_to_fastest_s,
        "stats": {
            "mean": s.mean,
            "median": s.median,
            "q1": s.q1,
            "q3": s.q3,
            "whisker_low": s.whisker_low,
            "whisker_high": s.whisker_high,
            "outliers": s.outliers,
            "n_laps": s.n_laps,
            "compounds": s.compounds,
        },
    }


@router.get("/weekends/{year}/{round}/pace")
def weekend_pace(
    year: int, round: int, session: str = "R", db: Session = Depends(get_session)
):
    w = _weekend(db, year, round)
    race = _session_of(db, w.id, session)
    if race is None:
        return {"drivers": [], "constructors": [], "stop_counts": {}, "stop_count_spread": 0}
    dc = _driver_constructor(db, race.id)
    stints = db.exec(select(Stint).where(Stint.session_id == race.id)).all()
    stint_dicts = [
        {
            "driver": s.driver,
            "constructor": dc.get(s.driver),
            "compound": s.compound,
            "lap_times": s.lap_times_json or [],
            "stint_number": s.stint_number,
        }
        for s in stints
    ]
    stop_counts = driver_stop_counts(stint_dicts)
    return {
        "drivers": [_pace_row_to_dict(r) for r in driver_distributions(stint_dicts)],
        "constructors": [_pace_row_to_dict(r) for r in constructor_distributions(stint_dicts)],
        # The box plot pools every stint per driver regardless of stop count, so gaps are
        # already pit-equated; these two fields just flag when that equalization is shakier.
        "stop_counts": stop_counts,
        "stop_count_spread": stop_count_spread(stop_counts),
    }


@router.get("/weekends/{year}/{round}/sectors")
def weekend_sectors(year: int, round: int, db: Session = Depends(get_session)):
    """Best sector 1/2/3 across all practice sessions, per driver, tagged with which
    session each best came from. Practice-only: indicative, since fuel loads and engine
    modes vary run to run."""
    w = _weekend(db, year, round)
    sessions = [s for s in _weekend_sessions(db, w.id) if s.session_type in PRACTICE_SESSIONS]
    if not sessions:
        return {"indicative": True, "drivers": [], "dominance": []}

    dc = _weekend_driver_constructor(db, w.id)
    rows = [
        {"driver": r.driver, "sector": r.sector, "best_time_s": r.best_time_s, "session_type": s.session_type}
        for s in sessions
        for r in db.exec(select(SectorBest).where(SectorBest.session_id == s.id)).all()
    ]
    bests = best_across_sessions(rows)
    enriched = [
        {"driver": b.driver, "sector": b.sector, "best_time_s": b.best_time_s, "constructor": dc.get(b.driver)}
        for b in bests
    ]
    dominance = sector_dominance(enriched)
    return {
        "indicative": True,
        "drivers": [
            {
                "driver": b.driver,
                "constructor": dc.get(b.driver),
                "sector": b.sector,
                "best_time_s": b.best_time_s,
                "session_type": b.session_type,
            }
            for b in bests
        ],
        "dominance": [
            {"sector": d.sector, "constructor": d.constructor, "best_time_s": d.best_time_s, "margin_s": d.margin_s}
            for d in dominance
        ],
    }


@router.get("/weekends/{year}/{round}/topspeeds")
def weekend_topspeeds(year: int, round: int, db: Session = Depends(get_session)):
    """Each driver's highest top speed across all practice sessions, km/h and mph, tagged
    with which session it came from. Practice-only: indicative."""
    w = _weekend(db, year, round)
    sessions = [s for s in _weekend_sessions(db, w.id) if s.session_type in PRACTICE_SESSIONS]
    if not sessions:
        return {"indicative": True, "drivers": []}

    dc = _weekend_driver_constructor(db, w.id)
    rows = [
        {"driver": r.driver, "session_type": s.session_type, "max_speed_kmh": r.max_speed_kmh}
        for s in sessions
        for r in db.exec(select(StraightSegment).where(StraightSegment.session_id == s.id)).all()
        if r.max_speed_kmh is not None
    ]
    bests = sorted(best_top_speeds(rows), key=lambda r: r["max_speed_kmh"], reverse=True)
    return {
        "indicative": True,
        "drivers": [
            {
                "driver": b["driver"],
                "constructor": dc.get(b["driver"]),
                "max_speed_kmh": b["max_speed_kmh"],
                "max_speed_mph": b["max_speed_kmh"] * 0.621371,
                "session_type": b["session_type"],
            }
            for b in bests
        ],
    }


@router.get("/weekends/{year}/{round}/quali-character")
def weekend_quali_character(year: int, round: int, db: Session = Depends(get_session)):
    """Car-character comparison from the top teams' fastest qualifying laps: lap time,
    top speed, minimum speed, speed through the fastest corner (picked once across the
    compared teams), and full-throttle percentage, with labels derived from those
    numbers. Limited to TOP_TEAMS_N teams so "leader" labels reflect the front of the
    field being compared, not diluted by the whole grid."""
    w = _weekend(db, year, round)
    sessions = _weekend_sessions(db, w.id)
    session = _session_by_type(sessions, "Q")
    if session is None:
        return {"session_type": None, "rows": [], "fastest_corner_number": None, "sector_dominance": []}

    qc_rows = db.exec(select(QualiCharacter).where(QualiCharacter.session_id == session.id)).all()
    driver_rows = [
        {
            "constructor": r.constructor,
            "driver": r.driver,
            "lap_time_s": r.lap_time_s,
            "top_speed_kmh": r.top_speed_kmh,
            "min_speed_kmh": r.min_speed_kmh,
            "full_throttle_pct": r.full_throttle_pct,
            "corner_speeds": {int(k): v for k, v in (r.corner_speeds_json or {}).items()},
        }
        for r in qc_rows
        if r.constructor and r.lap_time_s is not None
    ]
    reps = fastest_qualifier_per_constructor(driver_rows)[:TOP_TEAMS_N]
    labeled = label_car_character(reps)

    dc = _weekend_driver_constructor(db, w.id)
    sector_rows = [
        {"driver": r.driver, "sector": r.sector, "best_time_s": r.best_time_s, "constructor": dc.get(r.driver)}
        for r in db.exec(select(SectorBest).where(SectorBest.session_id == session.id)).all()
    ]
    dominance = sector_dominance(sector_rows)
    fastest_corner_number = pick_fastest_corner(reps)

    return {
        "session_type": session.session_type,
        "rows": [
            {
                "constructor": r.constructor,
                "driver": r.driver,
                "lap_time_s": r.lap_time_s,
                "top_speed_kmh": r.top_speed_kmh,
                "min_speed_kmh": r.min_speed_kmh,
                "full_throttle_pct": r.full_throttle_pct,
                "fastest_corner_kmh": r.fastest_corner_kmh,
                "drag_label": r.drag_label,
                "is_top_speed_leader": r.is_top_speed_leader,
                "is_corner_speed_leader": r.is_corner_speed_leader,
                "is_grip_leader": r.is_grip_leader,
            }
            for r in labeled
        ],
        "fastest_corner_number": fastest_corner_number,
        "sector_dominance": [
            {"sector": d.sector, "constructor": d.constructor, "best_time_s": d.best_time_s, "margin_s": d.margin_s}
            for d in dominance
        ],
    }


@router.get("/weekends/{year}/{round}/degradation")
def weekend_degradation(
    year: int, round: int, session: str = "R", db: Session = Depends(get_session)
):
    """Fuel-corrected lap time vs tyre age, per team and compound: the slope is the
    degradation rate, the cost is what that slope adds up to by a reference tyre age."""
    w = _weekend(db, year, round)
    race = _session_of(db, w.id, session)
    if race is None:
        return {"fits": [], "points": [], "reference_age_laps": None}

    dc = _driver_constructor(db, race.id)
    stints = db.exec(select(Stint).where(Stint.session_id == race.id)).all()
    points: list[dict] = []
    for st in stints:
        constructor = dc.get(st.driver)
        if constructor is None:
            continue
        ages = st.tyre_ages_json or []
        times = st.lap_times_json or []
        for age, t in zip(ages, times):
            if age is None:
                continue
            points.append(
                {"constructor": constructor, "compound": st.compound, "tyre_age": age, "lap_time_s": t}
            )

    fits = fit_all_groups(points)

    return {
        "reference_age_laps": REFERENCE_AGE_LAPS,
        "points": points,
        "fits": [
            {
                "constructor": f.constructor,
                "compound": f.compound,
                "slope_s_per_lap": f.slope_s_per_lap,
                "intercept_s": f.intercept_s,
                "cost_at_reference_s": f.cost_at_reference_s,
                "n_laps": f.n_laps,
                "flagged": f.flagged,
            }
            for f in fits
        ],
    }


@router.get("/weekends/{year}/{round}/results")
def weekend_results(
    year: int, round: int, session: str = "R", db: Session = Depends(get_session)
):
    w = _weekend(db, year, round)
    race = _session_of(db, w.id, session)
    if race is None:
        return []
    rows = db.exec(
        select(SessionResult)
        .where(SessionResult.session_id == race.id)
        .order_by(SessionResult.position)
    ).all()
    leader_laps = next((r.laps for r in rows if r.position == 1), None)

    # Per-driver compound sequence from the race stints, ordered by stint number.
    stints = db.exec(
        select(Stint).where(Stint.session_id == race.id).order_by(Stint.stint_number)
    ).all()
    compounds_by_driver: dict[str, list[str | None]] = {}
    for s in stints:
        compounds_by_driver.setdefault(s.driver, []).append(s.compound)

    def gap_or_time(r: SessionResult) -> str:
        if r.position == 1 and r.total_time_s is not None:
            return format_total_time(r.total_time_s) or "leader"
        return format_gap_label(r.position, r.gap_to_leader, r.laps, leader_laps, r.status)

    return [
        {
            "position": r.position,
            "driver": r.driver,
            "constructor": r.constructor,
            "gap_label": gap_or_time(r),
            "points": points_for_session(race.session_type, r.position),
            "strategy": strategy_string(compounds_by_driver.get(r.driver, [])),
        }
        for r in rows
    ]


def _session_sectors_payload(db: Session, session: SessionRow, dc: dict[str, str]) -> dict:
    rows = [
        {"driver": r.driver, "sector": r.sector, "best_time_s": r.best_time_s, "session_type": session.session_type}
        for r in db.exec(select(SectorBest).where(SectorBest.session_id == session.id)).all()
    ]
    bests = best_across_sessions(rows)
    dominance = sector_dominance(
        [
            {"driver": b.driver, "sector": b.sector, "best_time_s": b.best_time_s, "constructor": dc.get(b.driver)}
            for b in bests
        ]
    )
    return {
        "indicative": session.session_type in PRACTICE_SESSIONS or session.session_type == "SQ",
        "drivers": [
            {
                "driver": b.driver,
                "constructor": dc.get(b.driver),
                "sector": b.sector,
                "best_time_s": b.best_time_s,
                "session_type": b.session_type,
            }
            for b in bests
        ],
        "dominance": [
            {"sector": d.sector, "constructor": d.constructor, "best_time_s": d.best_time_s, "margin_s": d.margin_s}
            for d in dominance
        ],
    }


def _session_topspeeds_payload(db: Session, session: SessionRow, dc: dict[str, str]) -> dict:
    rows = [
        {"driver": r.driver, "session_type": session.session_type, "max_speed_kmh": r.max_speed_kmh}
        for r in db.exec(select(StraightSegment).where(StraightSegment.session_id == session.id)).all()
        if r.max_speed_kmh is not None
    ]
    bests = sorted(best_top_speeds(rows), key=lambda r: r["max_speed_kmh"], reverse=True)
    return {
        "indicative": session.session_type in PRACTICE_SESSIONS or session.session_type == "SQ",
        "drivers": [
            {
                "driver": b["driver"],
                "constructor": dc.get(b["driver"]),
                "max_speed_kmh": b["max_speed_kmh"],
                "max_speed_mph": b["max_speed_kmh"] * 0.621371,
                "session_type": b["session_type"],
            }
            for b in bests
        ],
    }


def _session_order_payload(db: Session, session: SessionRow) -> list[dict]:
    rows = db.exec(
        select(SessionResult)
        .where(SessionResult.session_id == session.id)
        .order_by(SessionResult.position)
    ).all()
    leader_laps = next((r.laps for r in rows if r.position == 1), None)

    def gap_or_time(r: SessionResult) -> str:
        if r.position == 1 and r.total_time_s is not None:
            return format_total_time(r.total_time_s) or "leader"
        return format_gap_label(r.position, r.gap_to_leader, r.laps, leader_laps, r.status)

    return [
        {
            "position": r.position,
            "driver": r.driver,
            "constructor": r.constructor,
            "gap_label": gap_or_time(r),
        }
        for r in rows
    ]


@router.get("/weekends/{year}/{round}/session-summary")
def weekend_session_summary(
    year: int, round: int, session: str, db: Session = Depends(get_session)
):
    """Light per-session read for sprint qualifying: sectors, top speeds, classification."""
    w = _weekend(db, year, round)
    ses = _session_of(db, w.id, session)
    if ses is None:
        return {
            "session_type": None,
            "sectors": {"indicative": True, "drivers": [], "dominance": []},
            "topspeeds": {"indicative": True, "drivers": []},
            "order": [],
        }

    dc = _driver_constructor(db, ses.id)
    return {
        "session_type": ses.session_type,
        "sectors": _session_sectors_payload(db, ses, dc),
        "topspeeds": _session_topspeeds_payload(db, ses, dc),
        "order": _session_order_payload(db, ses),
    }


@router.get("/season/{year}")
def season_snapshot(year: int, db: Session = Depends(get_session)):
    """Season-long rollup, one entry per constructor: overall rank (0.6 race / 0.4 quali),
    per-metric season means with spread, round-by-round trend, and a thin-data confidence
    flag. Every figure aggregates numbers already computed at the weekend level."""
    snapshot = build_season_snapshot(year, db)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="no weekends for year")
    return snapshot


@router.post("/subscribe")
def subscribe(body: SubscribeIn, db: Session = Depends(get_session)):
    existing = db.exec(select(Subscriber).where(Subscriber.email == body.email)).first()
    if existing:
        return {"status": "already_subscribed"}
    db.add(Subscriber(email=body.email, followed_constructor=body.followed_constructor))
    db.commit()
    return {"status": "subscribed"}
