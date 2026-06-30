"""Bound DB tools for the insight agent.

Every tool is a deterministic Postgres read. The agent retrieves numbers through these
tools; it never invents them. Tools are bound to one (year, round) at build time and use
an injected session factory so they can be exercised against a test database.

Returns are JSON strings so the tool output is auditable verbatim in source_tool_calls.
"""

import json

from sqlmodel import Session, select

from telogify.db import engine
from telogify.models import (
    Attribution,
    CandidateInsight,
    ConstructorIndex,
    RaceWeekend,
    Session as SessionRow,
    SessionResult,
    Stint,
    StraightSegment,
)


def _default_factory() -> Session:
    return Session(engine)


def _weekend_id(db: Session, year: int, round: int) -> int | None:
    w = db.exec(
        select(RaceWeekend).where(RaceWeekend.year == year, RaceWeekend.round == round)
    ).first()
    return w.id if w else None


def _session_id(db: Session, weekend_id: int, session_type: str) -> int | None:
    s = db.exec(
        select(SessionRow).where(
            SessionRow.weekend_id == weekend_id, SessionRow.session_type == session_type
        )
    ).first()
    return s.id if s else None


def build_tools(year: int, round: int, session_factory=None) -> list:
    """Return the 7 LangChain tools bound to this weekend."""
    from langchain_core.tools import tool

    sf = session_factory or _default_factory

    @tool
    def get_candidate_insights(n: int = 10) -> str:
        """Return the top n pre-computed candidate findings for this weekend, ranked by
        statistical robustness, highest first. Always call this first, then pick the three
        most robust to write up."""
        with sf() as db:
            wid = _weekend_id(db, year, round)
            rows = db.exec(
                select(CandidateInsight)
                .where(CandidateInsight.weekend_id == wid)
                .order_by(CandidateInsight.rank)
                .limit(n)
            ).all()
            return json.dumps(
                [
                    {
                        "rank": r.rank,
                        "category": r.category,
                        "signal_type": r.signal_type,
                        "magnitude": r.magnitude,
                        "confidence": r.confidence,
                        "robustness_score": r.robustness_score,
                        "source_refs": r.source_refs_json,
                    }
                    for r in rows
                ]
            )

    @tool
    def get_straight_speed(driver: str, session_type: str, drs_zone: int) -> str:
        """Max and trap speed (km/h) for a driver in one DRS zone of one session
        (session_type one of FP1/FP2/FP3/Q/SQ/SPRINT/R)."""
        with sf() as db:
            sid = _session_id(db, _weekend_id(db, year, round), session_type)
            seg = db.exec(
                select(StraightSegment).where(
                    StraightSegment.session_id == sid,
                    StraightSegment.driver == driver,
                    StraightSegment.drs_zone_id == drs_zone,
                )
            ).first()
            if seg is None:
                return json.dumps({"found": False})
            return json.dumps(
                {
                    "found": True,
                    "driver": driver,
                    "drs_zone": drs_zone,
                    "max_speed_kmh": seg.max_speed_kmh,
                    "trap_speed_kmh": seg.trap_speed_kmh,
                }
            )

    @tool
    def get_corner_delta(
        corner_number: int, constructor_a: str, constructor_b: str, session_type: str
    ) -> str:
        """Car-vs-driver attribution at a corner between two constructors. delta is the
        min-speed difference in km/h (constructor_a minus constructor_b); car_pct and
        driver_pct split that gap; confidence is 0-1."""
        with sf() as db:
            sid = _session_id(db, _weekend_id(db, year, round), session_type)
            row = db.exec(
                select(Attribution).where(
                    Attribution.session_id == sid,
                    Attribution.corner_number == corner_number,
                    Attribution.constructor_a.in_([constructor_a, constructor_b]),
                    Attribution.constructor_b.in_([constructor_a, constructor_b]),
                )
            ).first()
            if row is None:
                return json.dumps({"found": False})
            sign = 1.0 if row.constructor_a == constructor_a else -1.0
            return json.dumps(
                {
                    "found": True,
                    "corner_number": corner_number,
                    "speed_class": row.speed_class,
                    "min_speed_delta_kmh": (row.delta_s or 0.0) * sign,
                    "car_pct": row.car_pct,
                    "driver_pct": row.driver_pct,
                    "confidence": row.confidence,
                }
            )

    @tool
    def get_lap_evolution(driver: str, stint_number: int, compound: str) -> str:
        """Lap times (seconds) and average pace for one driver stint, to read tyre
        degradation. Searches the race, then any session."""
        with sf() as db:
            wid = _weekend_id(db, year, round)
            sids = [
                s.id for s in db.exec(select(SessionRow).where(SessionRow.weekend_id == wid)).all()
            ]
            row = db.exec(
                select(Stint).where(
                    Stint.session_id.in_(sids),
                    Stint.driver == driver,
                    Stint.stint_number == stint_number,
                )
            ).first()
            if row is None:
                return json.dumps({"found": False})
            return json.dumps(
                {
                    "found": True,
                    "driver": driver,
                    "stint_number": stint_number,
                    "compound": row.compound,
                    "avg_pace_s": row.avg_pace,
                    "lap_times_s": row.lap_times_json,
                }
            )

    @tool
    def get_session_results(session_type: str) -> str:
        """Finishing order for a session: position, driver, constructor, gap to leader (s),
        status."""
        with sf() as db:
            sid = _session_id(db, _weekend_id(db, year, round), session_type)
            rows = db.exec(
                select(SessionResult)
                .where(SessionResult.session_id == sid)
                .order_by(SessionResult.position)
            ).all()
            return json.dumps(
                [
                    {
                        "position": r.position,
                        "driver": r.driver,
                        "constructor": r.constructor,
                        "gap_to_leader_s": r.gap_to_leader,
                        "status": r.status,
                    }
                    for r in rows
                ]
            )

    @tool
    def get_stint_summary(driver: str) -> str:
        """All race stints for a driver: stint number, compound, lap range, average pace (s)."""
        with sf() as db:
            wid = _weekend_id(db, year, round)
            race_id = _session_id(db, wid, "R")
            rows = db.exec(
                select(Stint)
                .where(Stint.session_id == race_id, Stint.driver == driver)
                .order_by(Stint.stint_number)
            ).all()
            return json.dumps(
                [
                    {
                        "stint_number": r.stint_number,
                        "compound": r.compound,
                        "lap_start": r.lap_start,
                        "lap_end": r.lap_end,
                        "avg_pace_s": r.avg_pace,
                    }
                    for r in rows
                ]
            )

    @tool
    def get_constructor_ranking() -> str:
        """Teams ranked by real race pace this weekend: overall_rank (1 = fastest) and
        race_pace_gap_s, the seconds per lap each team was off the fastest team's pace."""
        with sf() as db:
            wid = _weekend_id(db, year, round)
            rows = db.exec(
                select(ConstructorIndex)
                .where(ConstructorIndex.weekend_id == wid)
                .order_by(ConstructorIndex.overall_rank)
            ).all()
            return json.dumps(
                [
                    {
                        "constructor": r.constructor,
                        "overall_rank": r.overall_rank,
                        "race_pace_gap_s": r.lap_deficit_s,
                    }
                    for r in rows
                ]
            )

    return [
        get_candidate_insights,
        get_straight_speed,
        get_corner_delta,
        get_lap_evolution,
        get_session_results,
        get_stint_summary,
        get_constructor_ranking,
    ]
