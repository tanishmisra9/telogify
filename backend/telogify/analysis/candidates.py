"""Candidate insight pre-computation.

Mine signals across all sessions, score each by robustness = normalized(|magnitude|)
* confidence (normalized PER signal type so a corner delta and a straight delta are
comparable), then correlate related single-session signals into stronger combined
candidates before ranking. The agent only ever sees this ranked, robustness-sorted list.

ponytail: four signal types cover the brief's required set. Add more types here, the
scoring/correlation/ranking stays unchanged.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from statistics import mean

from sqlmodel import Session as DBSession
from sqlmodel import delete, select

from telogify.analysis.attribution import _driver_constructor_map
from telogify.models import (
    Attribution,
    CandidateInsight,
    Session,
    SessionResult,
    StraightSegment,
    Stint,
)

POSITION_SWING_MIN = 2  # only notable grid-to-finish swings become signals


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


def _mine_race_pace(db, sessions, dc_map):
    race = next((s for s in sessions if s.session_type in ("R", "SPRINT")), None)
    if race is None:
        return []
    best: dict[str, float] = {}
    for st in db.exec(select(Stint).where(Stint.session_id == race.id)).all():
        constructor = dc_map.get(st.driver)
        if constructor is None or st.avg_pace is None:
            continue
        if constructor not in best or st.avg_pace < best[constructor]:
            best[constructor] = st.avg_pace
    if not best:
        return []
    fastest = min(best.values())
    out = []
    for constructor, pace in best.items():
        deficit = pace - fastest
        if deficit <= 0:
            continue
        out.append(
            Signal(
                signal_type="race_pace",
                category="pace",
                magnitude=deficit,
                confidence=1.0,
                subject=constructor,
                session_type=race.session_type,
                source_refs=[
                    {
                        "type": "race_pace",
                        "constructor": constructor,
                        "best_pace_s": pace,
                        "deficit_s": deficit,
                    }
                ],
            )
        )
    return out


def _mine_position_swings(db, sessions, dc_map):
    quali = next((s for s in sessions if s.session_type == "Q"), None)
    race = next((s for s in sessions if s.session_type == "R"), None)
    if quali is None or race is None:
        return []
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
        swing = start - r.position  # positive = positions gained
        if abs(swing) < POSITION_SWING_MIN:
            continue
        constructor = dc_map.get(r.driver) or r.constructor
        if constructor is None:
            continue
        out.append(
            Signal(
                signal_type="position_swing",
                category="result",
                magnitude=abs(swing),
                confidence=1.0,
                subject=constructor,
                session_type="R",
                source_refs=[
                    {
                        "type": "position_swing",
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


def compute_candidates(weekend_id: int, db: DBSession) -> list[Signal]:
    sessions = db.exec(select(Session).where(Session.weekend_id == weekend_id)).all()
    dc_map = _driver_constructor_map(db, [s.id for s in sessions])

    signals = (
        _mine_corner_deltas(db, sessions)
        + _mine_straight_deltas(db, sessions, dc_map)
        + _mine_race_pace(db, sessions, dc_map)
        + _mine_position_swings(db, sessions, dc_map)
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
