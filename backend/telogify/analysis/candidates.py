"""Candidate insight pre-computation.

Mine signals across all sessions, score each by robustness = normalized(|magnitude|)
* confidence (normalized PER signal type so a corner delta and a straight delta are
comparable), then correlate related single-session signals into stronger combined
candidates before ranking. The agent only ever sees this ranked, robustness-sorted list.

ponytail: signal types cover the brief's required set. Add more types here, the
scoring/correlation/ranking stays unchanged.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from statistics import mean

from sqlmodel import Session as DBSession
from sqlmodel import delete, select

from telogify.analysis.attribution import _driver_constructor_map
from telogify.analysis.degradation import fit_all_groups
from telogify.analysis.quali_character import fastest_qualifier_per_constructor
from telogify.analysis.race_pace import constructor_median_gaps
from telogify.analysis.sectors import best_across_sessions
from telogify.analysis.sessions import pick_session
from telogify.models import (
    Attribution,
    CandidateInsight,
    QualiCharacter,
    SectorBest,
    Session,
    SessionResult,
    StraightSegment,
    Stint,
)

POSITION_SWING_MIN = 2  # only notable grid-to-finish swings become signals
REAL_STRAIGHT_KMH = 300.0  # a zone only counts as a real top-speed straight if the field tops this
PRACTICE_SESSIONS = ("FP1", "FP2", "FP3")


@dataclass
class Signal:
    signal_type: str
    category: str
    magnitude: float  # signed or absolute; only |magnitude| feeds robustness
    confidence: float
    subject: str  # constructor the signal is about (correlation key)
    locus: str | None = None  # e.g. "zone:2" / "corner:7"
    session_type: str | None = None
    source_refs: list[dict] = field(default_factory=list)
    robustness: float = 0.0


# --- pure scoring / correlation / ranking ----------------------------------


def normalize_and_score(signals: list[Signal]) -> list[Signal]:
    """Set robustness = (|magnitude| / max|magnitude| within type) * confidence."""
    max_abs: dict[str, float] = defaultdict(float)
    for s in signals:
        max_abs[s.signal_type] = max(max_abs[s.signal_type], abs(s.magnitude))
    for s in signals:
        peak = max_abs[s.signal_type]
        norm = abs(s.magnitude) / peak if peak > 0 else 0.0
        s.robustness = norm * s.confidence
    return signals


def _merge(parts: list[Signal]) -> Signal:
    primary = max(parts, key=lambda s: s.robustness)
    merged = Signal(
        signal_type="cross_session",
        category="cross_session",
        magnitude=primary.magnitude,
        confidence=mean(p.confidence for p in parts),
        subject=primary.subject,
        locus=primary.locus,
        session_type=None,
        source_refs=[ref for p in parts for ref in p.source_refs],
    )
    # Corroborating signals stack: the sum strictly outranks each part (robustness may
    # exceed 1.0, which is fine since it is only ever used for ranking).
    merged.robustness = sum(p.robustness for p in parts)
    return merged


def correlate(signals: list[Signal]) -> list[Signal]:
    """Merge a constructor's straight-line deficit with its race position loss."""
    by_subject: dict[str, list[Signal]] = defaultdict(list)
    for s in signals:
        by_subject[s.subject].append(s)

    merged_parts: set[int] = set()
    out: list[Signal] = []
    for group in by_subject.values():
        straights = [s for s in group if s.signal_type == "straight_delta"]
        swings = [s for s in group if s.signal_type == "position_swing"]
        if straights and swings:
            parts = [max(straights, key=lambda s: s.robustness), max(swings, key=lambda s: s.robustness)]
            out.append(_merge(parts))
            merged_parts.update(id(p) for p in parts)

    out.extend(s for s in signals if id(s) not in merged_parts)
    return out


def rank(signals: list[Signal]) -> list[Signal]:
    return sorted(signals, key=lambda s: s.robustness, reverse=True)


# --- DB-side mining --------------------------------------------------------


def _mine_corner_deltas(db, sessions):
    sid_to_type = {s.id: s.session_type for s in sessions}
    out = []
    for attr in db.exec(
        select(Attribution).where(Attribution.session_id.in_(list(sid_to_type)))
    ).all():
        if attr.delta_s is None or attr.confidence is None:
            continue
        # delta_s = metric(a) - metric(b); the slower constructor (deficit) is the subject.
        slower = attr.constructor_b if attr.delta_s > 0 else attr.constructor_a
        out.append(
            Signal(
                signal_type="corner_delta",
                category="corner",
                magnitude=abs(attr.delta_s),
                confidence=attr.confidence,
                subject=slower,
                locus=f"corner:{attr.corner_number}",
                session_type=sid_to_type[attr.session_id],
                source_refs=[
                    {
                        "type": "corner_delta",
                        "session_type": sid_to_type[attr.session_id],
                        "corner_number": attr.corner_number,
                        "speed_class": attr.speed_class,
                        "constructor_a": attr.constructor_a,
                        "constructor_b": attr.constructor_b,
                        "min_speed_delta_kmh": abs(attr.delta_s),
                        "car_pct": attr.car_pct,
                        "driver_pct": attr.driver_pct,
                    }
                ],
            )
        )
    return out


def _mine_straight_deltas(db, sessions, dc_map):
    out = []
    for session in sessions:
        segs = db.exec(
            select(StraightSegment).where(StraightSegment.session_id == session.id)
        ).all()
        # constructor mean max speed per zone
        by_zone: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for seg in segs:
            constructor = dc_map.get(seg.driver)
            if constructor and seg.max_speed_kmh is not None:
                by_zone[seg.drs_zone_id][constructor].append(seg.max_speed_kmh)
        for zone, by_con in by_zone.items():
            con_speed = {c: mean(v) for c, v in by_con.items()}
            if len(con_speed) < 2:
                continue
            fastest = max(con_speed.values())
            if fastest < REAL_STRAIGHT_KMH:
                continue  # an inter-corner squirt, not a real straight; skip
            leader = max(con_speed, key=con_speed.get)
            for constructor, speed in con_speed.items():
                deficit = fastest - speed
                if deficit <= 0:
                    continue
                out.append(
                    Signal(
                        signal_type="straight_delta",
                        category="straight",
                        magnitude=deficit,
                        confidence=1.0,
                        subject=constructor,
                        locus=f"zone:{zone}",
                        session_type=session.session_type,
                        source_refs=[
                            {
                                "type": "straight_delta",
                                "session_type": session.session_type,
                                "drs_zone": zone,
                                "constructor": constructor,
                                "deficit_kmh": deficit,
                                "fastest_constructor": leader,
                                "fastest_speed_kmh": fastest,
                            }
                        ],
                    )
                )
    return out


def _mine_race_pace_for_session(
    db, session: Session, dc_map: dict[str, str], signal_type: str
) -> list[Signal]:
    stints = db.exec(select(Stint).where(Stint.session_id == session.id)).all()
    stint_dicts = [
        {
            "driver": st.driver,
            "constructor": dc_map.get(st.driver),
            "compound": st.compound,
            "lap_times": st.lap_times_json or [],
        }
        for st in stints
        if dc_map.get(st.driver)
    ]

    deficits = constructor_median_gaps(stint_dicts)
    if not deficits:
        return []

    out = []
    for constructor, deficit in deficits.items():
        if deficit <= 0:
            continue
        out.append(
            Signal(
                signal_type=signal_type,
                category="pace",
                magnitude=deficit,
                confidence=1.0,
                subject=constructor,
                session_type=session.session_type,
                source_refs=[
                    {
                        "type": signal_type,
                        "constructor": constructor,
                        "deficit_s": deficit,
                        "session_type": session.session_type,
                    }
                ],
            )
        )
    return out


def _mine_race_pace(db, sessions, dc_map):
    out: list[Signal] = []
    race = pick_session(sessions, ("R",))
    if race is not None:
        out.extend(_mine_race_pace_for_session(db, race, dc_map, "race_pace"))
    sprint = pick_session(sessions, ("SPRINT",))
    if sprint is not None:
        out.extend(_mine_race_pace_for_session(db, sprint, dc_map, "sprint_pace"))
    return out


def _mine_position_swings_for_pair(
    db,
    quali: Session,
    race: Session,
    dc_map: dict[str, str],
    signal_type: str,
    session_type: str,
) -> list[Signal]:
    grid = {
        r.driver: r.position
        for r in db.exec(select(SessionResult).where(SessionResult.session_id == quali.id)).all()
        if r.position is not None
    }
    out = []
    for r in db.exec(select(SessionResult).where(SessionResult.session_id == race.id)).all():
        start = grid.get(r.driver)
        if start is None or r.position is None:
            continue
        swing = start - r.position
        if abs(swing) < POSITION_SWING_MIN:
            continue
        constructor = dc_map.get(r.driver) or r.constructor
        if constructor is None:
            continue
        out.append(
            Signal(
                signal_type=signal_type,
                category="result",
                magnitude=abs(swing),
                confidence=1.0,
                subject=constructor,
                session_type=session_type,
                source_refs=[
                    {
                        "type": signal_type,
                        "driver": r.driver,
                        "constructor": constructor,
                        "grid": start,
                        "finish": r.position,
                        "positions_gained": swing,
                    }
                ],
            )
        )
    return out


def _mine_position_swings(db, sessions, dc_map):
    out: list[Signal] = []
    quali = pick_session(sessions, ("Q",))
    race = pick_session(sessions, ("R",))
    if quali is not None and race is not None:
        out.extend(_mine_position_swings_for_pair(db, quali, race, dc_map, "position_swing", "R"))
    sq = pick_session(sessions, ("SQ",))
    sprint = pick_session(sessions, ("SPRINT",))
    if sq is not None and sprint is not None:
        out.extend(
            _mine_position_swings_for_pair(db, sq, sprint, dc_map, "sprint_position_swing", "SPRINT")
        )
    return out


def _mine_sector_deltas(db, sessions, dc_map):
    """Practice best-sector deficits, per constructor per sector, vs the fastest
    constructor in that sector. Feeds the same candidate pool as corner/straight
    deltas so a practice weakness can corroborate a race-pace or position signal."""
    practice = [s for s in sessions if s.session_type in PRACTICE_SESSIONS]
    if not practice:
        return []

    rows = [
        {"driver": r.driver, "sector": r.sector, "best_time_s": r.best_time_s, "session_type": s.session_type}
        for s in practice
        for r in db.exec(select(SectorBest).where(SectorBest.session_id == s.id)).all()
    ]
    bests = best_across_sessions(rows)

    by_sector: dict[int, dict[str, float]] = defaultdict(dict)
    for b in bests:
        constructor = dc_map.get(b.driver)
        if constructor is None:
            continue
        cur = by_sector[b.sector].get(constructor)
        if cur is None or b.best_time_s < cur:
            by_sector[b.sector][constructor] = b.best_time_s

    out = []
    for sector, by_constructor in by_sector.items():
        if len(by_constructor) < 2:
            continue
        fastest = min(by_constructor.values())
        for constructor, best_time in by_constructor.items():
            deficit = best_time - fastest
            if deficit <= 0:
                continue
            out.append(
                Signal(
                    signal_type="sector_delta",
                    category="sector",
                    magnitude=deficit,
                    confidence=1.0,
                    subject=constructor,
                    locus=f"sector:{sector}",
                    session_type="practice",
                    source_refs=[
                        {
                            "type": "sector_delta",
                            "sector": sector,
                            "constructor": constructor,
                            "best_time_s": best_time,
                            "deficit_s": deficit,
                            "fastest_time_s": fastest,
                        }
                    ],
                )
            )
    return out


def _mine_quali_character_for_session(db, session: Session) -> list[Signal]:
    rows = db.exec(select(QualiCharacter).where(QualiCharacter.session_id == session.id)).all()
    driver_rows = [
        {
            "constructor": r.constructor,
            "driver": r.driver,
            "lap_time_s": r.lap_time_s,
            "top_speed_kmh": r.top_speed_kmh,
        }
        for r in rows
        if r.constructor and r.lap_time_s is not None and r.top_speed_kmh is not None
    ]
    reps = fastest_qualifier_per_constructor(driver_rows)
    if len(reps) < 2:
        return []

    fastest = max(r["top_speed_kmh"] for r in reps)
    out = []
    for r in reps:
        deficit = fastest - r["top_speed_kmh"]
        if deficit <= 0:
            continue
        out.append(
            Signal(
                signal_type="quali_top_speed_delta",
                category="quali_character",
                magnitude=deficit,
                confidence=1.0,
                subject=r["constructor"],
                session_type=session.session_type,
                source_refs=[
                    {
                        "type": "quali_top_speed_delta",
                        "constructor": r["constructor"],
                        "driver": r["driver"],
                        "top_speed_kmh": r["top_speed_kmh"],
                        "deficit_kmh": deficit,
                        "fastest_top_speed_kmh": fastest,
                        "session_type": session.session_type,
                    }
                ],
            )
        )
    return out


def _mine_quali_character(db, sessions):
    """Qualifying top-speed deficit per constructor, from each team's fastest lap.
    Complements straight_delta (which is corner-gap based) with a single-lap read
    tied directly to the qualifying car-character block."""
    out: list[Signal] = []
    for session_type in ("Q", "SQ"):
        session = pick_session(sessions, (session_type,))
        if session is not None:
            out.extend(_mine_quali_character_for_session(db, session))
    return out


def _mine_degradation_for_session(
    db, session: Session, dc_map: dict[str, str], signal_type: str
) -> list[Signal]:
    stints = db.exec(select(Stint).where(Stint.session_id == session.id)).all()
    points = []
    for st in stints:
        constructor = dc_map.get(st.driver)
        if constructor is None:
            continue
        for age, t in zip(st.tyre_ages_json or [], st.lap_times_json or []):
            if age is None:
                continue
            points.append({"constructor": constructor, "compound": st.compound, "tyre_age": age, "lap_time_s": t})

    out = []
    for fit in fit_all_groups(points):
        if fit.slope_s_per_lap <= 0:
            continue
        out.append(
            Signal(
                signal_type=signal_type,
                category="degradation",
                magnitude=fit.cost_at_reference_s,
                confidence=1.0,
                subject=fit.constructor,
                locus=f"compound:{fit.compound}",
                session_type=session.session_type,
                source_refs=[
                    {
                        "type": signal_type,
                        "constructor": fit.constructor,
                        "compound": fit.compound,
                        "slope_s_per_lap": fit.slope_s_per_lap,
                        "cost_at_reference_s": fit.cost_at_reference_s,
                        "n_laps": fit.n_laps,
                        "flagged": fit.flagged,
                        "session_type": session.session_type,
                    }
                ],
            )
        )
    return out


def _mine_degradation(db, sessions, dc_map):
    """Race tyre-degradation cost per constructor per compound, from fuel-corrected
    lap time vs tyre age. Only positive (real wear) slopes produce a signal."""
    out: list[Signal] = []
    race = pick_session(sessions, ("R",))
    if race is not None:
        out.extend(_mine_degradation_for_session(db, race, dc_map, "tyre_degradation"))
    sprint = pick_session(sessions, ("SPRINT",))
    if sprint is not None:
        out.extend(_mine_degradation_for_session(db, sprint, dc_map, "sprint_degradation"))
    return out


def _mine_sprint_vs_race_pace(db, sessions, dc_map) -> list[Signal]:
    """Per-constructor delta of sprint median pace vs race median pace on the same weekend."""
    sprint = pick_session(sessions, ("SPRINT",))
    race = pick_session(sessions, ("R",))
    if sprint is None or race is None:
        return []

    def median_gaps_for(session: Session) -> dict[str, float]:
        stints = db.exec(select(Stint).where(Stint.session_id == session.id)).all()
        stint_dicts = [
            {
                "driver": st.driver,
                "constructor": dc_map.get(st.driver),
                "compound": st.compound,
                "lap_times": st.lap_times_json or [],
            }
            for st in stints
            if dc_map.get(st.driver)
        ]
        return constructor_median_gaps(stint_dicts)

    sprint_gaps = median_gaps_for(sprint)
    race_gaps = median_gaps_for(race)
    constructors = set(sprint_gaps) & set(race_gaps)
    if not constructors:
        return []

    out = []
    for constructor in constructors:
        delta = sprint_gaps[constructor] - race_gaps[constructor]
        if delta == 0:
            continue
        out.append(
            Signal(
                signal_type="sprint_race_pace_delta",
                category="cross_event",
                magnitude=abs(delta),
                confidence=1.0,
                subject=constructor,
                session_type=None,
                source_refs=[
                    {
                        "type": "sprint_race_pace_delta",
                        "constructor": constructor,
                        "sprint_median_gap_s": sprint_gaps[constructor],
                        "race_median_gap_s": race_gaps[constructor],
                        "delta_s": delta,
                    }
                ],
            )
        )
    return out


def compute_candidates(weekend_id: int, db: DBSession) -> list[Signal]:
    sessions = db.exec(select(Session).where(Session.weekend_id == weekend_id)).all()
    dc_map = _driver_constructor_map(db, [s.id for s in sessions])

    signals = (
        _mine_corner_deltas(db, sessions)
        + _mine_straight_deltas(db, sessions, dc_map)
        + _mine_race_pace(db, sessions, dc_map)
        + _mine_position_swings(db, sessions, dc_map)
        + _mine_sector_deltas(db, sessions, dc_map)
        + _mine_quali_character(db, sessions)
        + _mine_degradation(db, sessions, dc_map)
        + _mine_sprint_vs_race_pace(db, sessions, dc_map)
    )
    normalize_and_score(signals)
    ranked = rank(correlate(signals))

    db.exec(delete(CandidateInsight).where(CandidateInsight.weekend_id == weekend_id))
    for i, s in enumerate(ranked):
        db.add(
            CandidateInsight(
                weekend_id=weekend_id,
                rank=i + 1,
                category=s.category,
                signal_type=s.signal_type,
                magnitude=s.magnitude,
                confidence=s.confidence,
                robustness_score=s.robustness,
                source_refs_json={"subject": s.subject, "refs": s.source_refs},
            )
        )
    db.commit()
    return ranked
