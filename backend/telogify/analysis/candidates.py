"""Candidate insight pre-computation.

Mine signals across all sessions, score each by robustness = normalized(|magnitude|)
* confidence (normalized PER signal type so a corner delta and a straight delta are
comparable), discount findings that are readable straight from the results table, then
fuse every constructor's signals that span multiple data channels into one cross-channel
candidate that outranks any single-channel signal. The agent only ever sees this ranked,
robustness-sorted list.

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
from telogify.analysis.season import build_season_snapshot
from telogify.analysis.sectors import best_across_sessions
from telogify.analysis.sessions import pick_session
from telogify.ingest.wikipedia_parse import fact_mentions_driver
from telogify.models import (
    Attribution,
    CandidateInsight,
    DeploymentTrace,
    QualiCharacter,
    RaceWeekend,
    SectorBest,
    Session,
    SessionResult,
    StraightSegment,
    Stint,
    WeekendRecap,
)

POSITION_SWING_MIN = 2  # only notable grid-to-finish swings become signals
REAL_STRAIGHT_KMH = 300.0  # a zone only counts as a real top-speed straight if the field tops this
# Single-corner and single-straight cross-team deltas above these are almost always a
# segmentation/alignment artifact (a corner window that sampled the wrong corner, or a
# 'straight' segment that caught a braking zone), not a real car difference. Drop them so a
# bogus 99 km/h corner gap or 67 km/h straight deficit never reaches the agent.
MAX_CORNER_DELTA_KMH = 18.0
MAX_STRAIGHT_DEFICIT_KMH = 20.0
PRACTICE_SESSIONS = ("FP1", "FP2", "FP3")
# Findings fully readable from the finishing/grid table (position swings) are obvious to
# anyone who watched the race; halve their standalone score so they only reach the top by
# fusing with a telemetry channel that explains them (see correlate).
OBVIOUS_CATEGORIES = {"result"}
OBVIOUSNESS_DISCOUNT = 0.5
# A team that finished exactly where its season-long pace says it should has no story worth
# telling ("backmarker is slow"); damp all its signals toward this floor. Over- and
# under-deliverers (finished far from their expected order) keep near-full strength.
EXPECTATION_FLOOR = 0.15


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


def expectation_factors(
    expected_rank: dict[str, int], actual_rank: dict[str, int]
) -> dict[str, float]:
    """Per-constructor damping factor in [EXPECTATION_FLOOR, 1.0] from how far a team's actual
    finishing order sits from where its season pace ranks it. |delta| alone captures every
    genre: a big gap either way (over- or under-delivery) stays near 1.0; finishing to
    expectation lands at the floor. A team missing from either ordering is left out (the
    caller treats an absent subject as neutral 1.0)."""
    common = set(expected_rank) & set(actual_rank)
    span = max(len(actual_rank) - 1, 1)  # widest possible |delta| across the ranked field
    out: dict[str, float] = {}
    for c in common:
        delta = abs(expected_rank[c] - actual_rank[c])
        out[c] = EXPECTATION_FLOOR + (1 - EXPECTATION_FLOOR) * min(1.0, delta / span)
    return out


def normalize_and_score(
    signals: list[Signal], expectation_factor: dict[str, float] | None = None
) -> list[Signal]:
    """Set robustness = (|magnitude| / max|magnitude| within type) * confidence, discounted for
    obvious findings and damped by each subject's expectation factor (absent subject -> 1.0)."""
    max_abs: dict[str, float] = defaultdict(float)
    for s in signals:
        max_abs[s.signal_type] = max(max_abs[s.signal_type], abs(s.magnitude))
    for s in signals:
        peak = max_abs[s.signal_type]
        norm = abs(s.magnitude) / peak if peak > 0 else 0.0
        s.robustness = norm * s.confidence
        if s.category in OBVIOUS_CATEGORIES:
            s.robustness *= OBVIOUSNESS_DISCOUNT
        if expectation_factor is not None:
            s.robustness *= expectation_factor.get(s.subject, 1.0)
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
    """Fuse every constructor's signals that span 2+ data channels into one cross-channel
    candidate: a finding built from several channels (e.g. a qualifying top-speed deficit
    AND a sector weakness AND a race position lost) sums the robustness of its strongest
    signal per channel, so the more channels point the same way the higher it ranks. This
    is the cross-channel bonus, and it is also how an obvious position swing earns a top
    slot: only by pairing with a telemetry channel that explains it. Single-channel
    subjects pass through unchanged."""
    by_subject: dict[str, list[Signal]] = defaultdict(list)
    for s in signals:
        by_subject[s.subject].append(s)

    out: list[Signal] = []
    for group in by_subject.values():
        best_per_channel: dict[str, Signal] = {}
        for s in group:
            cur = best_per_channel.get(s.category)
            if cur is None or s.robustness > cur.robustness:
                best_per_channel[s.category] = s
        if len(best_per_channel) >= 2:
            out.append(_merge(list(best_per_channel.values())))
        else:
            out.extend(group)  # one channel only: nothing to cross-reference
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
        if abs(attr.delta_s) > MAX_CORNER_DELTA_KMH:
            continue  # implausible single-corner min-speed gap => misaligned corner window
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
                if deficit > MAX_STRAIGHT_DEFICIT_KMH:
                    continue  # implausible straight-line deficit => segment wasn't a clean straight
                out.append(
                    Signal(
                        signal_type="straight_delta",
                        category="straight",
                        magnitude=deficit,
                        confidence=1.0,
                        subject=constructor,
                        locus=f"straight:{zone}",
                        session_type=session.session_type,
                        source_refs=[
                            {
                                "type": "straight_delta",
                                "session_type": session.session_type,
                                "straight_number": zone,
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
            "gaps_to_car_ahead": st.gaps_to_car_ahead_json or [],
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
            "min_speed_kmh": r.min_speed_kmh,
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

    # Mechanical-grip read: deficit in the slowest-corner minimum speed vs the field's best. A
    # distinct quali channel from top speed, so a car strong in a straight but weak in the slow
    # stuff (or the reverse) can surface as the non-obvious finding.
    grip_reps = [r for r in reps if r.get("min_speed_kmh") is not None]
    if len(grip_reps) >= 2:
        best_grip = max(r["min_speed_kmh"] for r in grip_reps)
        for r in grip_reps:
            deficit = best_grip - r["min_speed_kmh"]
            if deficit <= 0:
                continue
            out.append(
                Signal(
                    signal_type="quali_grip_delta",
                    category="quali_character",
                    magnitude=deficit,
                    confidence=1.0,
                    subject=r["constructor"],
                    session_type=session.session_type,
                    source_refs=[
                        {
                            "type": "quali_grip_delta",
                            "constructor": r["constructor"],
                            "driver": r["driver"],
                            "min_speed_kmh": r["min_speed_kmh"],
                            "deficit_kmh": deficit,
                            "best_min_speed_kmh": best_grip,
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


_QUALI_PROGRESSION_MIN_DEVIATION_S = 0.05


def _mine_quali_progression_for_session(db, session: Session) -> list[Signal]:
    """Q1->Q3 (or Q1->Q2, if eliminated in Q2) improvement per constructor's fastest car,
    compared against the field average improvement: a car that found unusually more or less
    time across the hour than its rivals is a genuine session-to-session story."""
    rows = db.exec(select(SessionResult).where(SessionResult.session_id == session.id)).all()
    candidates: list[dict] = []
    for r in rows:
        if r.constructor is None or r.q1_time_s is None:
            continue
        if r.q3_time_s is not None:
            delta, reached = r.q1_time_s - r.q3_time_s, "Q3"
        elif r.q2_time_s is not None:
            delta, reached = r.q1_time_s - r.q2_time_s, "Q2"
        else:
            continue
        candidates.append(
            {
                "constructor": r.constructor,
                "driver": r.driver,
                "delta_s": delta,
                "reached": reached,
                "q1_time_s": r.q1_time_s,
                "q2_time_s": r.q2_time_s,
                "q3_time_s": r.q3_time_s,
            }
        )
    if len(candidates) < 3:
        return []

    best_per_constructor: dict[str, dict] = {}
    for c in candidates:
        final_time = c["q3_time_s"] if c["q3_time_s"] is not None else c["q2_time_s"]
        existing = best_per_constructor.get(c["constructor"])
        existing_final = (
            existing["q3_time_s"] if existing and existing["q3_time_s"] is not None else (existing["q2_time_s"] if existing else None)
        )
        if existing is None or final_time < existing_final:
            best_per_constructor[c["constructor"]] = c
    reps = list(best_per_constructor.values())
    if len(reps) < 3:
        return []

    field_avg = mean(r["delta_s"] for r in reps)
    out: list[Signal] = []
    for r in reps:
        deviation = r["delta_s"] - field_avg
        if abs(deviation) < _QUALI_PROGRESSION_MIN_DEVIATION_S:
            continue
        out.append(
            Signal(
                signal_type="quali_progression",
                category="quali_character",
                magnitude=abs(deviation),
                confidence=0.8,
                subject=r["constructor"],
                session_type=session.session_type,
                source_refs=[
                    {
                        "type": "quali_progression",
                        "constructor": r["constructor"],
                        "driver": r["driver"],
                        "q1_time_s": r["q1_time_s"],
                        "q2_time_s": r["q2_time_s"],
                        "q3_time_s": r["q3_time_s"],
                        "improvement_s": r["delta_s"],
                        "field_average_improvement_s": field_avg,
                        "reached": r["reached"],
                        "session_type": session.session_type,
                    }
                ],
            )
        )
    return out


def _mine_quali_progression(db, sessions):
    out: list[Signal] = []
    for session_type in ("Q", "SQ"):
        session = pick_session(sessions, (session_type,))
        if session is not None:
            out.extend(_mine_quali_progression_for_session(db, session))
    return out


def linear_regression(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    """Ordinary least squares slope/intercept for y ~ x. None if x has no spread."""
    n = len(xs)
    if n < 2:
        return None
    mean_x, mean_y = mean(xs), mean(ys)
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom
    intercept = mean_y - slope * mean_x
    return slope, intercept


_QUALI_RESIDUAL_MIN_S = 0.05


def _mine_quali_pace_speed_correlation_for_session(db, session: Session) -> list[Signal]:
    """Residual of lap time regressed against top speed, per constructor's fastest qualifier: a
    car whose lap time is much quicker or slower than its top speed alone predicts is winning or
    losing that lap somewhere other than the straights."""
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
    if len(reps) < 4:
        return []

    fit = linear_regression([r["top_speed_kmh"] for r in reps], [r["lap_time_s"] for r in reps])
    if fit is None:
        return []
    slope, intercept = fit

    out: list[Signal] = []
    for r in reps:
        predicted = slope * r["top_speed_kmh"] + intercept
        residual = r["lap_time_s"] - predicted
        if abs(residual) < _QUALI_RESIDUAL_MIN_S:
            continue
        out.append(
            Signal(
                signal_type="quali_pace_speed_residual",
                category="quali_character",
                magnitude=abs(residual),
                confidence=0.75,
                subject=r["constructor"],
                session_type=session.session_type,
                source_refs=[
                    {
                        "type": "quali_pace_speed_residual",
                        "constructor": r["constructor"],
                        "driver": r["driver"],
                        "lap_time_s": r["lap_time_s"],
                        "top_speed_kmh": r["top_speed_kmh"],
                        "predicted_lap_time_s": predicted,
                        "residual_s": residual,
                        "session_type": session.session_type,
                    }
                ],
            )
        )
    return out


def _mine_quali_pace_speed_correlation(db, sessions):
    out: list[Signal] = []
    for session_type in ("Q", "SQ"):
        session = pick_session(sessions, (session_type,))
        if session is not None:
            out.extend(_mine_quali_pace_speed_correlation_for_session(db, session))
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
            points.append({"constructor": constructor, "driver": st.driver, "compound": st.compound, "tyre_age": age, "lap_time_s": t})

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


def _expected_ranks(weekend_id: int, db: DBSession) -> dict[str, int]:
    """Constructor -> season pace+quali rank (1 = best car), from the season snapshot."""
    weekend = db.get(RaceWeekend, weekend_id)
    if weekend is None:
        return {}
    # ponytail: snapshot spans every ingested round of the year, so re-running an early round
    # with later rounds present leaks their pace into "expected"; add a max_round arg if backfilling.
    snapshot = build_season_snapshot(weekend.year, db)
    if snapshot is None:
        return {}
    return {
        r["constructor"]: r["overall_rank"]
        for r in snapshot["constructors"]
        if r.get("overall_rank") is not None
    }


def _actual_ranks(sessions: list[Session], db: DBSession) -> dict[str, int]:
    """Constructor -> this weekend's finishing rank (1 = best), by each team's best race finish."""
    race = pick_session(sessions, ("R",))
    if race is None:
        return {}
    best: dict[str, int] = {}
    for r in db.exec(select(SessionResult).where(SessionResult.session_id == race.id)).all():
        if r.position is None or r.constructor is None:
            continue
        cur = best.get(r.constructor)
        if cur is None or r.position < cur:
            best[r.constructor] = r.position
    ordered = sorted(best, key=lambda c: best[c])
    return {c: i + 1 for i, c in enumerate(ordered)}


def _mine_deployment(db, sessions):
    """ERS deployment weakness: a car that clips more (its speed falls at full throttle before the
    braking zone) runs out of electrical deployment sooner and is passable at the end of straights.
    Per-constructor mean clip distance on the qualifying lap, as a deficit to the field's best
    (lowest-clipping) car. A distinct 'deployment' channel, so it can fuse with a race outcome."""
    out = []
    for stype in ("Q", "SQ"):
        session = pick_session(sessions, (stype,))
        if session is None:
            continue
        rows = db.exec(
            select(DeploymentTrace).where(DeploymentTrace.session_id == session.id)
        ).all()
        by_con: dict[str, list] = defaultdict(list)
        for r in rows:
            if r.constructor:
                by_con[r.constructor].append(r)
        if len(by_con) < 2:
            continue
        # Consistency gate: clipping is a CAR trait only if BOTH the team's cars show it. A single
        # car clipping is one lap's energy strategy / traffic, not a reliable weakness. Use the min
        # across the clipping cars (what the car does on both), which is robust to one noisy lap.
        con_clip: dict[str, float] = {}
        for c, rs in by_con.items():
            clippers = [r for r in rs if r.max_clip_m > 0]
            if len(clippers) >= 2:
                con_clip[c] = min(r.total_clip_m for r in clippers)
        if len(con_clip) < 2:
            continue
        best = min(con_clip.values())
        for c in con_clip:
            rs = by_con[c]
            deficit = con_clip[c] - best
            if deficit <= 0:
                continue
            worst = max(
                (st for r in rs for st in (r.straights_json or []) if st.get("is_clip")),
                key=lambda st: st["clip_m"],
                default=None,
            )
            out.append(
                Signal(
                    signal_type="deployment_clip",
                    category="deployment",
                    magnitude=deficit,
                    confidence=1.0,
                    subject=c,
                    session_type=stype,
                    source_refs=[
                        {
                            "type": "deployment_clip",
                            "constructor": c,
                            "total_clip_m": round(con_clip[c]),
                            "excess_clip_m": round(deficit),
                            "field_best_clip_m": round(best),
                            "worst_straight": worst,
                            "session_type": stype,
                        }
                    ],
                )
            )
    return out


_RECAP_KIND_WEIGHT: dict[str, float] = {
    "damage": 1.0,
    "retirement": 0.95,
    "penalty": 0.9,
    "collision": 0.85,
    "safety_car": 0.7,
    "strategy": 0.5,
    "weather": 0.4,
    "other": 0.3,
}


def _mine_recap_outcomes(
    db: DBSession,
    weekend_id: int,
    sessions: list[Session],
    dc_map: dict[str, str],
) -> list[Signal]:
    """Grid-to-finish swings with matching Wikipedia race-recap facts AND a quantified race-pace
    deficit for that constructor: recap only stands as a candidate when it can explain a real
    number, never as a standalone event narrative."""
    recap = db.exec(select(WeekendRecap).where(WeekendRecap.weekend_id == weekend_id)).first()
    if recap is None or not recap.sessions_json:
        return []
    r_data = recap.sessions_json.get("R") or {}
    if not r_data.get("present"):
        return []
    facts: list[dict] = r_data.get("facts") or []
    if not facts:
        return []

    quali = pick_session(sessions, ("Q",))
    race = pick_session(sessions, ("R",))
    if quali is None or race is None:
        return []

    stints = db.exec(select(Stint).where(Stint.session_id == race.id)).all()
    stint_dicts = [
        {
            "driver": st.driver,
            "constructor": dc_map.get(st.driver),
            "compound": st.compound,
            "lap_times": st.lap_times_json or [],
            "gaps_to_car_ahead": st.gaps_to_car_ahead_json or [],
        }
        for st in stints
        if dc_map.get(st.driver)
    ]
    pace_deficits = constructor_median_gaps(stint_dicts)

    grid = {
        r.driver: r.position
        for r in db.exec(select(SessionResult).where(SessionResult.session_id == quali.id)).all()
        if r.driver and r.position is not None
    }

    out: list[Signal] = []
    for r in db.exec(select(SessionResult).where(SessionResult.session_id == race.id)).all():
        start = grid.get(r.driver) if r.driver else None
        if start is None or r.position is None or r.driver is None:
            continue
        swing = start - r.position
        if abs(swing) < POSITION_SWING_MIN:
            continue
        matching = [f for f in facts if fact_mentions_driver(f, r.driver)]
        if not matching:
            continue
        constructor = dc_map.get(r.driver) or r.constructor
        if constructor is None:
            continue
        pace_deficit = pace_deficits.get(constructor)
        if pace_deficit is None or pace_deficit <= 0:
            continue
        kind_weight = max(_RECAP_KIND_WEIGHT.get(f.get("kind", "other"), 0.3) for f in matching)
        swing_abs = abs(swing)
        swing_boost = 1.5 if swing_abs >= 10 else 1.0
        out.append(
            Signal(
                signal_type="recap_outcome",
                category="recap",
                magnitude=swing_abs * kind_weight * swing_boost,
                confidence=kind_weight,
                subject=constructor,
                session_type="R",
                source_refs=[
                    {
                        "type": "recap_outcome",
                        "driver": r.driver,
                        "constructor": constructor,
                        "grid": start,
                        "finish": r.position,
                        "positions_gained": swing,
                        "recap_facts": matching,
                        "pace_deficit_s": pace_deficit,
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
        + _mine_recap_outcomes(db, weekend_id, sessions, dc_map)
        + _mine_sector_deltas(db, sessions, dc_map)
        + _mine_quali_character(db, sessions)
        + _mine_quali_progression(db, sessions)
        + _mine_quali_pace_speed_correlation(db, sessions)
        + _mine_deployment(db, sessions)
        + _mine_degradation(db, sessions, dc_map)
        + _mine_sprint_vs_race_pace(db, sessions, dc_map)
    )
    factors = expectation_factors(
        _expected_ranks(weekend_id, db), _actual_ranks(sessions, db)
    )
    normalize_and_score(signals, factors)
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
