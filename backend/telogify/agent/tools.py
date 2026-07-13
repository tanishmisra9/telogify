"""Bound DB tools for the insight agent.

Every tool is a deterministic Postgres read. The agent retrieves numbers through these
tools; it never invents them. Tools are bound to one (year, round) at build time and use
an injected session factory so they can be exercised against a test database.

Returns are JSON strings so the tool output is auditable verbatim in source_tool_calls.
"""

import json
from collections import defaultdict
from statistics import mean

from sqlmodel import Session, select

from telogify.analysis.candidates import _ERS_HARVEST_BAND_KMH, _ERS_MIN_BAND_POINTS, linear_regression
from telogify.analysis.quali_character import (
    TOP_TEAMS_N,
    fastest_qualifier_per_constructor,
    label_car_character,
    pick_fastest_corner,
)
from telogify.analysis.sectors import sector_dominance
from telogify.db import engine
from telogify.models import (
    AccelSample,
    Attribution,
    CandidateInsight,
    ConstructorIndex,
    DeploymentTrace,
    QualiCharacter,
    RaceControlEvent,
    RaceWeekend,
    SectorBest,
    Session as SessionRow,
    SessionResult,
    Stint,
    StraightSegment,
)


_KMH_TO_MPH = 0.621371


def _mph(kmh: float | None) -> float | None:
    if kmh is None:
        return None
    return round(kmh * _KMH_TO_MPH, 1)


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


def build_tools(year: int, round_num: int, session_factory=None) -> list:
    """Return the LangChain tools bound to this weekend."""
    from langchain_core.tools import tool

    sf = session_factory or _default_factory

    @tool
    def get_candidate_insights(n: int = 10, category: str = "") -> str:
        """Return the top n pre-computed candidate findings for this weekend, ranked highest
        first. The ranking favors teams that beat or fell short of where their car's season-long
        pace level should have put them (over- and under-delivery), not just the biggest raw
        gaps, and rewards findings that combine channels. Always call this first, then pick the
        three strongest to write up. Pass category="quali_character" to see only qualifying
        car-character candidates (top-speed/grip deltas, quali progression, pace-vs-speed
        residual); blank for all categories."""
        with sf() as db:
            wid = _weekend_id(db, year, round_num)
            query = select(CandidateInsight).where(CandidateInsight.weekend_id == wid)
            if category:
                query = query.where(CandidateInsight.category == category)
            rows = db.exec(query.order_by(CandidateInsight.rank).limit(n)).all()
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
            sid = _session_id(db, _weekend_id(db, year, round_num), session_type)
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
                    "max_speed_mph": _mph(seg.max_speed_kmh),
                    "trap_speed_kmh": seg.trap_speed_kmh,
                    "trap_speed_mph": _mph(seg.trap_speed_kmh),
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
            sid = _session_id(db, _weekend_id(db, year, round_num), session_type)
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
            delta_kmh = (row.delta_s or 0.0) * sign
            return json.dumps(
                {
                    "found": True,
                    "corner_number": corner_number,
                    "speed_class": row.speed_class,
                    "min_speed_delta_kmh": delta_kmh,
                    "min_speed_delta_mph": _mph(delta_kmh),
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
            wid = _weekend_id(db, year, round_num)
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
            sid = _session_id(db, _weekend_id(db, year, round_num), session_type)
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
    def get_stint_summary(driver: str, session_type: str = "R") -> str:
        """All stints for a driver in a session (R or SPRINT): stint number, compound, lap range, average pace (s)."""
        with sf() as db:
            wid = _weekend_id(db, year, round_num)
            session_id = _session_id(db, wid, session_type)
            rows = db.exec(
                select(Stint)
                .where(Stint.session_id == session_id, Stint.driver == driver)
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
            wid = _weekend_id(db, year, round_num)
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

    @tool
    def get_race_control_events(driver: str = "", session_type: str = "R") -> str:
        """Official race control events (collisions, penalties, safety cars, forced-off moves, and
        steward-noted incidents) for the race ("R") or sprint ("SPRINT"), each with kind, lap,
        driver, and message. kind incident is NOTED or under investigation only, not a collision
        and not a retirement cause. Pass a driver's 3-letter code to filter, or blank for all.
        Call before attributing a finishing-position drop to car pace: only collision, forced-off,
        or penalty kinds explain a result. Noted incidents may be cited on their lap but must not
        be linked to a retirement or DNF. Returns [] when nothing notable happened."""
        with sf() as db:
            sid = _session_id(db, _weekend_id(db, year, round_num), session_type)
            if sid is None:
                return json.dumps([])
            q = select(RaceControlEvent).where(RaceControlEvent.session_id == sid)
            if driver:
                q = q.where(RaceControlEvent.driver == driver)
            rows = db.exec(q.order_by(RaceControlEvent.lap)).all()
            return json.dumps(
                [{"lap": r.lap, "driver": r.driver, "kind": r.kind, "message": r.message} for r in rows]
            )

    @tool
    def get_deployment(driver: str = "", session_type: str = "Q") -> str:
        """ERS deployment / clipping on the qualifying lap ("Q" or "SQ"): deploy depletion and
        super-clipping inferred from acceleration residuals at wide-open throttle. Per driver:
        top_speed_kmh, total_clip_m (depletion + superclip, higher = runs out sooner),
        total_depletion_m, total_superclip_m, max_clip_m, max_clip_severity_ms2, and per-straight
        clip segments. Pass a 3-letter code to filter, blank for all."""
        with sf() as db:
            sid = _session_id(db, _weekend_id(db, year, round_num), session_type)
            if sid is None:
                return json.dumps([])
            q = select(DeploymentTrace).where(DeploymentTrace.session_id == sid)
            if driver:
                q = q.where(DeploymentTrace.driver == driver)
            rows = db.exec(q.order_by(DeploymentTrace.total_clip_m.desc())).all()
            return json.dumps(
                [
                    {
                        "driver": r.driver,
                        "constructor": r.constructor,
                        "top_speed_kmh": r.top_speed_kmh,
                        "top_speed_mph": _mph(r.top_speed_kmh),
                        "total_clip_m": r.total_clip_m,
                        "total_depletion_m": r.total_depletion_m,
                        "total_superclip_m": r.total_superclip_m,
                        "max_clip_m": r.max_clip_m,
                        "max_clip_severity_ms2": r.max_clip_severity_ms2,
                        "clip_straights": [st for st in (r.straights_json or []) if st.get("is_clip")],
                    }
                    for r in rows
                ]
            )

    @tool
    def get_race_deployment_character(constructor: str = "") -> str:
        """Race-pace ERS deployment/harvesting character per constructor: how much full-throttle
        acceleration rises with speed through the 150-250 km/h harvesting-dominant band, from
        full-throttle/no-brake/low-lateral-g samples on one representative race lap per driver.
        harvesting_slope_ms2_per_kmh: a steep positive slope means harvesting ramps up hard with
        speed; a flat slope near the field average means the car deploys/harvests near-constantly
        across that range. This is a measured acceleration-vs-speed shape only: do not infer
        battery state, harvesting strategy, or software behavior from it. Pass a constructor name
        to filter, blank for all. Returns [] when there are too few cars with data this weekend."""
        with sf() as db:
            wid = _weekend_id(db, year, round_num)
            sid = _session_id(db, wid, "R") if wid is not None else None
            if sid is None:
                return json.dumps([])
            samples = db.exec(select(AccelSample).where(AccelSample.session_id == sid)).all()
            by_constructor: dict[str, list[tuple[float, float]]] = defaultdict(list)
            for s in samples:
                if s.constructor:
                    by_constructor[s.constructor].extend(
                        zip(s.speed_kmh_json or [], s.longitudinal_accel_ms2_json or [])
                    )
            lo, hi = _ERS_HARVEST_BAND_KMH
            slopes: dict[str, tuple[float, int]] = {}
            for c, points in by_constructor.items():
                band = [(sp, ac) for sp, ac in points if lo <= sp <= hi]
                if len(band) < _ERS_MIN_BAND_POINTS:
                    continue
                fit = linear_regression([p[0] for p in band], [p[1] for p in band])
                if fit is not None:
                    slopes[c] = (fit[0], len(band))
            if len(slopes) < 3:
                return json.dumps([])
            field_avg = mean(v[0] for v in slopes.values())
            rows = [
                {
                    "constructor": c,
                    "harvesting_slope_ms2_per_kmh": round(slope, 4),
                    "field_average_slope": round(field_avg, 4),
                    "n_points": n,
                    "band_kmh": list(_ERS_HARVEST_BAND_KMH),
                }
                for c, (slope, n) in slopes.items()
                if not constructor or c == constructor
            ]
            rows.sort(key=lambda r: r["harvesting_slope_ms2_per_kmh"])
            return json.dumps(rows)

    @tool
    def get_quali_character() -> str:
        """Car-character comparison from the top teams' fastest qualifying laps: lap time, top
        speed, minimum speed (mechanical grip), speed through the fastest corner (picked once
        across the compared teams, so every team's downforce is read through the same corner),
        and full-throttle percentage, per constructor's fastest qualifier. drag_label is a
        rank-relative read within the compared teams: "efficient, low drag", "draggy,
        high-downforce", "lacks efficiency", or "balanced". is_top_speed_leader /
        is_corner_speed_leader / is_grip_leader flag the single best car on that metric.
        sector_dominance names, per sector, the constructor with the best time and its margin
        over the next-best. Limited to the top teams by qualifying pace so labels reflect the
        front of the field, not the whole grid."""
        with sf() as db:
            wid = _weekend_id(db, year, round_num)
            sid = _session_id(db, wid, "Q") if wid is not None else None
            if sid is None:
                return json.dumps(
                    {"rows": [], "fastest_corner_number": None, "sector_dominance": []}
                )
            qc_rows = db.exec(select(QualiCharacter).where(QualiCharacter.session_id == sid)).all()
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

            dc = {r.driver: r.constructor for r in qc_rows if r.constructor}
            sector_rows = [
                {"driver": r.driver, "sector": r.sector, "best_time_s": r.best_time_s, "constructor": dc.get(r.driver)}
                for r in db.exec(select(SectorBest).where(SectorBest.session_id == sid)).all()
            ]
            dominance = sector_dominance(sector_rows)

            return json.dumps(
                {
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
                    "fastest_corner_number": pick_fastest_corner(reps),
                    "sector_dominance": [
                        {
                            "sector": d.sector,
                            "constructor": d.constructor,
                            "best_time_s": d.best_time_s,
                            "margin_s": d.margin_s,
                        }
                        for d in dominance
                    ],
                }
            )

    return [
        get_candidate_insights,
        get_race_control_events,
        get_deployment,
        get_race_deployment_character,
        get_quali_character,
        get_straight_speed,
        get_corner_delta,
        get_lap_evolution,
        get_session_results,
        get_stint_summary,
        get_constructor_ranking,
    ]
