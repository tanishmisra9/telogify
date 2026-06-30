"""Constructor index: confidence-weighted high/mid/low scores, overall rank, lap deficit.

Per (session, corner) each constructor's advantage is its min_speed minus the corner's
field mean (km/h). Advantages are aggregated per speed class with a CONFIDENCE-WEIGHTED
MEAN, so a team seen at more corners cannot score higher just for having more data
points. Lap deficit (seconds) comes from best race-stint pace versus the field's best.
"""

from collections import defaultdict
from dataclasses import dataclass
from statistics import mean

from sqlmodel import Session as DBSession
from sqlmodel import delete, select

from telogify.analysis.attribution import (
    _driver_constructor_map,
    _session_driver_corners,
    classify_speed,
    driver_confidence,
)
from telogify.models import ConstructorIndex, Session, Stint


@dataclass
class CornerScore:
    speed_class: str  # low / mid / high
    advantage: float  # km/h vs the corner field mean
    confidence: float


def weighted_mean(pairs: list[tuple[float, float]]) -> float | None:
    """pairs: [(value, weight)] -> confidence-weighted mean, or None if no weight."""
    total = sum(w for _, w in pairs)
    if total <= 0:
        return None
    return sum(v * w for v, w in pairs) / total


def summarize_constructor(scores: list[CornerScore]) -> dict[str, float | None]:
    """high/mid/low/overall confidence-weighted means from a constructor's corner scores."""

    def band(cls: str) -> float | None:
        return weighted_mean([(s.advantage, s.confidence) for s in scores if s.speed_class == cls])

    overall = weighted_mean([(s.advantage, s.confidence) for s in scores])
    return {
        "high": band("high"),
        "mid": band("mid"),
        "low": band("low"),
        "overall": overall,
    }


def rank_constructors(overalls: dict[str, float | None]) -> dict[str, int]:
    """Rank by overall advantage, highest first. Constructors with no score rank last."""
    ranked = sorted(
        overalls.items(),
        key=lambda kv: (kv[1] is None, -(kv[1] or 0.0)),
    )
    return {constructor: i + 1 for i, (constructor, _) in enumerate(ranked)}


def lap_deficits(best_pace: dict[str, float]) -> dict[str, float]:
    """Per-constructor seconds behind the field's best race pace."""
    if not best_pace:
        return {}
    fastest = min(best_pace.values())
    return {c: pace - fastest for c, pace in best_pace.items()}


# --- DB-side orchestration -------------------------------------------------


def _race_best_pace(db: DBSession, sessions: list[Session], dc_map: dict[str, str]):
    race = next((s for s in sessions if s.session_type in ("R", "SPRINT")), None)
    if race is None:
        return {}
    stints = db.exec(select(Stint).where(Stint.session_id == race.id)).all()
    best: dict[str, float] = {}
    for st in stints:
        constructor = dc_map.get(st.driver)
        if constructor is None or st.avg_pace is None:
            continue
        if constructor not in best or st.avg_pace < best[constructor]:
            best[constructor] = st.avg_pace
    return best


def build_constructor_index(weekend_id: int, db: DBSession) -> None:
    sessions = db.exec(select(Session).where(Session.weekend_id == weekend_id)).all()
    dc_map = _driver_constructor_map(db, [s.id for s in sessions])

    per_constructor: dict[str, list[CornerScore]] = defaultdict(list)
    for session in sessions:
        corners = _session_driver_corners(db, session.id, dc_map)
        for drivers in corners.values():
            by_constructor: dict[str, list] = defaultdict(list)
            for d in drivers:
                by_constructor[d.constructor].append(d)
            if len(by_constructor) < 2:
                continue  # need a field to measure advantage against
            metric = {c: mean(x.metric for x in ds) for c, ds in by_constructor.items()}
            field = mean(metric.values())
            speed_class = classify_speed(field)
            for c, ds in by_constructor.items():
                conf = driver_confidence(min(x.clean_laps for x in ds))
                per_constructor[c].append(CornerScore(speed_class, metric[c] - field, conf))

    summaries = {c: summarize_constructor(scores) for c, scores in per_constructor.items()}
    deficits = lap_deficits(_race_best_pace(db, sessions, dc_map))

    # Rank by real race pace (smallest deficit first); the corner scores are kept only as
    # supporting detail. A team with no race pace ranks last.
    constructors = set(summaries) | set(deficits)
    ordered = sorted(constructors, key=lambda c: (c not in deficits, deficits.get(c, 0.0)))
    ranks = {c: i + 1 for i, c in enumerate(ordered)}

    db.exec(delete(ConstructorIndex).where(ConstructorIndex.weekend_id == weekend_id))
    for constructor in constructors:
        summary = summaries.get(constructor, {"high": None, "mid": None, "low": None})
        db.add(
            ConstructorIndex(
                weekend_id=weekend_id,
                constructor=constructor,
                high_score=summary["high"],
                mid_score=summary["mid"],
                low_score=summary["low"],
                overall_rank=ranks.get(constructor),
                lap_deficit_s=deficits.get(constructor),
            )
        )
    db.commit()
