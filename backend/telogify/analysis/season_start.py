"""Season race starts: per round, how far each team / power unit's launch was from that round's
best, then a recency-weighted season read. Aggregation of the SAME per-driver `RaceStart` numbers
the weekend card shows, not a new measurement. Teams and power units only (a season of drivers is
unreadable).

Per round and group the figure is the MEDIAN of the group's cars on the round's metric: the full
0-200 km/h time when the round has one, else the 0-100 time (Monaco/Baku: most cars brake for
turn 1 before 200). The gap is `% slower than the round's best group`, an index like the
qualifying gap, so rounds on either metric share one axis.

The two metrics are NOT like-for-like, though: on the rounds that have both, the field's spread of
team gaps is ~1.3x wider on 0-100 than on 0-200 (7.9% vs 6.0%, 2026). So 0-100-only rounds are
plotted but kept OUT of the weighted gap, the flat mean and the form ranks (unless the whole
season has no 0-200 round, in which case they are all there is).

Pure functions; `build_season_start` is the thin DB orchestrator.
"""

from collections import defaultdict
from statistics import median

from sqlmodel import Session as DBSession
from sqlmodel import select

from telogify.analysis.season import weighted_aggregate
from telogify.analysis.season_deployment import PU_GROUPS, pu_map_applies
from telogify.models import RaceStart, RaceWeekend, Session

# Rank movement needs enough rounds to mean anything.
MIN_ROUNDS_FOR_FORM = 4

Car = dict  # {"constructor": str, "t_0_100_s": float, "t_0_200_s": float | None}


def round_gaps(cars: list[Car], group_of) -> tuple[int, dict[str, dict]]:
    """(metric, {group: {gap_pct, gap_s, n_cars}}) for ONE round. `metric` is 200 when any car
    has a 0-200 time (only those cars count), else 100. `group_of(constructor)` -> key or None
    (an unmapped constructor is left out, never guessed)."""
    metric = 200 if any(c.get("t_0_200_s") is not None for c in cars) else 100
    field = "t_0_200_s" if metric == 200 else "t_0_100_s"
    pooled: dict[str, list[float]] = defaultdict(list)
    for c in cars:
        key = group_of(c["constructor"]) if c.get("constructor") else None
        if key is None or c.get(field) is None:
            continue
        pooled[key].append(c[field])
    meds = {k: median(v) for k, v in pooled.items()}
    if not meds:
        return metric, {}
    best = min(meds.values())
    return metric, {
        k: {"gap_pct": (v - best) / best * 100.0, "gap_s": v - best, "n_cars": len(pooled[k])}
        for k, v in meds.items()
    }


def build_view(
    rounds: list[tuple[int, list[Car]]], group_of, labels: dict[str, tuple[str, str]], current_round: int
) -> list[dict]:
    """One view (teams or power units): a row per group with its real per-round points (no
    interpolation), recency-weighted and flat season gaps, and rank movement. `labels` maps
    key -> (display label, colour team). Rows are sorted by the weighted gap, best first."""
    points: dict[str, list[dict]] = defaultdict(list)
    for rnd, cars in rounds:
        metric, gaps = round_gaps(cars, group_of)
        for key, g in gaps.items():
            points[key].append({"round": rnd, "metric": metric, **g})

    any_full = any(p["metric"] == 200 for ps in points.values() for p in ps)
    rows: list[dict] = []
    for key, ps in points.items():
        used = [p for p in ps if p["metric"] == 200] if any_full else ps
        agg = weighted_aggregate([(p["round"], p["gap_pct"]) for p in used], current_round)
        flat = sum(p["gap_pct"] for p in used) / len(used) if used else None
        label, color_team = labels.get(key, (key, key))
        rows.append(
            {
                "key": key,
                "label": label,
                "color_team": color_team,
                "points": sorted(ps, key=lambda p: p["round"]),
                "weighted_gap_pct": agg["mean"],
                "flat_gap_pct": flat,
                "n_rounds": len(used),
            }
        )

    def rank_by(field: str) -> dict[str, int]:
        ranked = sorted((r for r in rows if r[field] is not None), key=lambda r: r[field])
        return {r["key"]: i + 1 for i, r in enumerate(ranked)}

    rw, rf = rank_by("weighted_gap_pct"), rank_by("flat_gap_pct")
    for r in rows:
        r["rank_weighted"] = rw.get(r["key"])
        r["rank_flat"] = rf.get(r["key"])
        # Positive = ranks higher on recent form than over the whole season.
        r["form_places"] = (
            r["rank_flat"] - r["rank_weighted"]
            if r["n_rounds"] >= MIN_ROUNDS_FOR_FORM and r["rank_weighted"] and r["rank_flat"]
            else None
        )
    return sorted(rows, key=lambda r: (r["weighted_gap_pct"] is None, r["weighted_gap_pct"] or 0.0))


def build_season_start(year: int, db: DBSession) -> dict:
    """`{rounds, views}`: `views.teams` always (when any data), `views.pu` only when the supply map
    describes this season AND covers every team in it. Empty `views` when there is no data."""
    weekends = db.exec(select(RaceWeekend).where(RaceWeekend.year == year).order_by(RaceWeekend.round)).all()
    rounds_meta = [{"round": w.round, "event_name": w.event_name} for w in weekends]
    if not weekends:
        return {"rounds": [], "views": {}}

    by_round: list[tuple[int, list[Car]]] = []
    for w in weekends:
        race = db.exec(select(Session).where(Session.weekend_id == w.id, Session.session_type == "R")).first()
        if race is None:
            continue
        starts = db.exec(select(RaceStart).where(RaceStart.session_id == race.id)).all()
        cars = [
            {"constructor": s.constructor, "t_0_100_s": s.t_0_100_s, "t_0_200_s": s.t_0_200_s} for s in starts
        ]
        if cars:
            by_round.append((w.round, cars))
    if not by_round:
        return {"rounds": rounds_meta, "views": {}}

    current_round = weekends[-1].round
    teams = {c["constructor"] for _, cars in by_round for c in cars if c.get("constructor")}
    views = {"teams": {"rows": build_view(by_round, lambda c: c, {t: (t, t) for t in teams}, current_round)}}

    team_to_pu = {t: g.name for g in PU_GROUPS for t in g.teams}
    if pu_map_applies(year, teams):
        labels = {g.name: (g.name, g.works_team) for g in PU_GROUPS}
        views["pu"] = {"rows": build_view(by_round, team_to_pu.get, labels, current_round)}
    return {"rounds": rounds_meta, "views": views}
