"""Season Snapshot: cross-round rollup of already-computed per-weekend team metrics.

Nothing here is a new class of number. Each weekend's per-constructor figures (race-pace
gap, qualifying gap, top-speed deficit, sector dominance, tyre degradation) come from the
SAME analysis functions the weekend endpoints use, then get averaged across the season per
team. Aggregation, not new analysis.

The pure functions (aggregate / _normalize / overall_ranking / confidence) are unit-tested
offline; build_season_snapshot is the thin DB orchestrator, mirroring constructor_index.py.
"""

from collections import defaultdict
from statistics import mean, median, pstdev

from sqlmodel import Session as DBSession
from sqlmodel import select

from telogify.analysis.attribution import _driver_constructor_map
from telogify.analysis.sessions import pick_session
from telogify.analysis.degradation import fit_all_groups
from telogify.analysis.quali_character import fastest_qualifier_per_constructor
from telogify.analysis.race_pace import constructor_median_gaps
from telogify.analysis.sectors import sector_dominance
from telogify.models import QualiCharacter, RaceWeekend, SectorBest, Session, Stint

# Weighting locked with the user: race pace 60%, qualifying 40%.
RACE_WEIGHT = 0.6
QUALI_WEIGHT = 0.4
_KMH_TO_MPH = 0.621371


# --- pure aggregation ------------------------------------------------------


def aggregate(values: list[float | None]) -> dict:
    """{mean, spread, n} over a metric's per-round values; spread = population stdev
    (0.0 for a single round, so a consistent team reads differently from a swingy one).
    No values -> all None."""
    vals = [v for v in values if v is not None]
    if not vals:
        return {"mean": None, "spread": None, "n": 0}
    return {"mean": mean(vals), "spread": pstdev(vals) if len(vals) > 1 else 0.0, "n": len(vals)}


def _normalize(means: dict[str, float | None]) -> dict[str, float]:
    """Min-max each team's mean deficit onto 0..1 (0 = best/smallest, 1 = worst). Teams with
    no value are dropped; a single team maps to 0.0."""
    present = {c: m for c, m in means.items() if m is not None}
    if not present:
        return {}
    lo, hi = min(present.values()), max(present.values())
    span = hi - lo
    if span == 0:
        return {c: 0.0 for c in present}
    return {c: (m - lo) / span for c, m in present.items()}


def overall_ranking(
    pace_means: dict[str, float | None], quali_means: dict[str, float | None]
) -> dict[str, dict]:
    """Blend normalized race-pace and qualifying deficits (0.6/0.4), rank ascending
    (lower score = faster overall). Returns {constructor: {"score", "rank"}}.

    A team missing one metric is scored on the other alone rather than sunk; a team missing
    both is omitted here and ranked last by the caller.
    """
    npace = _normalize(pace_means)
    nquali = _normalize(quali_means)
    scores: dict[str, float] = {}
    for c in set(npace) | set(nquali):
        p, q = npace.get(c), nquali.get(c)
        if p is not None and q is not None:
            scores[c] = RACE_WEIGHT * p + QUALI_WEIGHT * q
        else:
            scores[c] = p if p is not None else q  # ponytail: one-metric team scored on it alone
    ordered = sorted(scores, key=lambda c: scores[c])
    return {c: {"score": scores[c], "rank": i + 1} for i, c in enumerate(ordered)}


def _reference_compound(deg_vals: dict[str, list[tuple[str, float, int]]]) -> str | None:
    """The compound the field ran the most laps on across the season. Comparing every team's
    degradation on this one tyre keeps it apples-to-apples (compounds have different baselines)."""
    laps: dict[str, int] = defaultdict(int)
    for fits in deg_vals.values():
        for compound, _slope, n in fits:
            laps[compound] += n
    return max(laps, key=laps.get) if laps else None


def _tyre_deg_on_ref(fits: list[tuple[str, float, int]], ref_compound: str | None) -> float | None:
    """Median degradation slope on the reference compound; falls back to all compounds pooled
    for a team that never ran the reference tyre (so it is still ranked, just less comparably)."""
    on_ref = [s for compound, s, _n in fits if compound == ref_compound]
    vals = on_ref or [s for _c, s, _n in fits]
    return median(vals) if vals else None


def confidence(n_rounds_with_data: int, total_rounds: int) -> str:
    """Season-view thin-data flag: a team seen in few of the season's rounds reads as lower
    confidence rather than being averaged in as equal to a full-season sample."""
    if total_rounds <= 0 or n_rounds_with_data == 0:
        return "low"
    frac = n_rounds_with_data / total_rounds
    if frac >= 0.75:
        return "high"
    if frac >= 0.4:
        return "med"
    return "low"


# --- DB orchestration ------------------------------------------------------


def _weekend_metrics(db: DBSession, dc_map: dict[str, str], sessions: list[Session]) -> dict[str, dict]:
    """Per-constructor metrics for one weekend, each as {constructor: value}, reusing the
    weekend-level analysis functions over the same source tables the weekend routes read."""
    out: dict[str, dict] = {
        "pace_gap": {},
        "quali_gap_pct": {},
        "top_speed_deficit_kmh": {},
        "sector_dominance_count": {},
        "tyre_deg": {},
    }

    # Race: pace gap AND tyre degradation from one load of the race stints.
    race = pick_session(sessions, ("R", "SPRINT"))
    if race is not None:
        stints = db.exec(select(Stint).where(Stint.session_id == race.id)).all()
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
        out["pace_gap"] = constructor_median_gaps(stint_dicts)

        deg_points = [
            {"constructor": dc_map[st.driver], "driver": st.driver, "compound": st.compound, "tyre_age": age, "lap_time_s": t}
            for st in stints
            if dc_map.get(st.driver)
            for age, t in zip(st.tyre_ages_json or [], st.lap_times_json or [])
            if age is not None
        ]
        # Keep each per-(compound) slope WITH its compound and lap count. The season rollup
        # compares teams on a single reference compound (see build_season_snapshot): pooling
        # compounds with different baselines (HARD wears more than MEDIUM) confounds the car's
        # own tyre handling with which tyre it happened to run.
        slopes: dict[str, list[tuple[str, float, int]]] = defaultdict(list)
        for f in fit_all_groups(deg_points):
            slopes[f.constructor].append((f.compound, f.slope_s_per_lap, f.n_laps))
        out["tyre_deg"] = dict(slopes)

    # Qualifying: gap %, top-speed deficit, sector dominance count.
    quali = pick_session(sessions, ("Q", "SQ"))
    if quali is not None:
        qc = db.exec(select(QualiCharacter).where(QualiCharacter.session_id == quali.id)).all()
        rows = [
            {"constructor": r.constructor, "lap_time_s": r.lap_time_s, "top_speed_kmh": r.top_speed_kmh}
            for r in qc
            if r.constructor and r.lap_time_s is not None
        ]
        reps = fastest_qualifier_per_constructor(rows)
        if reps:
            fastest = reps[0]["lap_time_s"]
            out["quali_gap_pct"] = {
                r["constructor"]: (r["lap_time_s"] - fastest) / fastest * 100.0 for r in reps
            }

        tops: dict[str, float] = {}
        for r in qc:
            if r.constructor and r.top_speed_kmh is not None:
                tops[r.constructor] = max(tops.get(r.constructor, 0.0), r.top_speed_kmh)
        if tops:
            session_best = max(tops.values())
            out["top_speed_deficit_kmh"] = {c: session_best - v for c, v in tops.items()}

        sec_rows = [
            {"driver": r.driver, "sector": r.sector, "best_time_s": r.best_time_s, "constructor": dc_map.get(r.driver)}
            for r in db.exec(select(SectorBest).where(SectorBest.session_id == quali.id)).all()
        ]
        counts: dict[str, int] = defaultdict(int)
        for d in sector_dominance(sec_rows):
            counts[d.constructor] += 1
        out["sector_dominance_count"] = dict(counts)

    return out


def build_season_snapshot(year: int, db: DBSession) -> dict | None:
    """Roll every ingested weekend of `year` up into one per-constructor season view.
    Returns None when the year has no weekends."""
    weekends = db.exec(
        select(RaceWeekend).where(RaceWeekend.year == year).order_by(RaceWeekend.round.asc())
    ).all()
    if not weekends:
        return None

    pace_vals: dict[str, list] = defaultdict(list)
    quali_vals: dict[str, list] = defaultdict(list)
    top_speed_vals: dict[str, list] = defaultdict(list)
    deg_vals: dict[str, list] = defaultdict(list)
    sector_totals: dict[str, int] = defaultdict(int)
    pace_trend: dict[str, list] = defaultdict(list)
    quali_trend: dict[str, list] = defaultdict(list)
    rounds_with_data: dict[str, set] = defaultdict(set)
    rounds_meta: list[dict] = []

    for w in weekends:
        sessions = db.exec(select(Session).where(Session.weekend_id == w.id)).all()
        dc_map = _driver_constructor_map(db, [s.id for s in sessions])
        m = _weekend_metrics(db, dc_map, sessions)
        rounds_meta.append({"round": w.round, "event_name": w.event_name})

        for c, v in m["pace_gap"].items():
            pace_vals[c].append(v)
            pace_trend[c].append({"round": w.round, "value": v})
            rounds_with_data[c].add(w.round)
        for c, v in m["quali_gap_pct"].items():
            quali_vals[c].append(v)
            quali_trend[c].append({"round": w.round, "value": v})
            rounds_with_data[c].add(w.round)
        for c, v in m["top_speed_deficit_kmh"].items():
            top_speed_vals[c].append(v)
        for c, v in m["tyre_deg"].items():
            deg_vals[c].extend(v)  # (compound, slope, n_laps) per fit; reduced on a reference compound below
        for c, v in m["sector_dominance_count"].items():
            sector_totals[c] += v

    constructors = set().union(pace_vals, quali_vals, top_speed_vals, deg_vals, sector_totals)
    total_rounds = len(weekends)

    # Tyre wear is compared on ONE reference compound (the one the field ran the most laps on),
    # so a team's number reflects its car, not which tyre it happened to run. Median over that
    # compound's fits is robust to a stray short-stint slope.
    ref_compound = _reference_compound(deg_vals)

    pace_means = {c: aggregate(pace_vals[c])["mean"] for c in constructors}
    quali_means = {c: aggregate(quali_vals[c])["mean"] for c in constructors}
    ranking = overall_ranking(pace_means, quali_means)
    unranked = len(constructors) + 1

    rows = []
    for c in sorted(constructors, key=lambda c: ranking.get(c, {}).get("rank", unranked)):
        ts = aggregate(top_speed_vals[c])
        rows.append(
            {
                "constructor": c,
                "overall_rank": ranking.get(c, {}).get("rank"),
                "pace_gap": aggregate(pace_vals[c]),
                "quali_gap_pct": aggregate(quali_vals[c]),
                "top_speed_deficit_kmh": ts["mean"],
                "top_speed_deficit_mph": ts["mean"] * _KMH_TO_MPH if ts["mean"] is not None else None,
                "sector_dominance_count": sector_totals.get(c, 0),
                "tyre_deg_s_per_lap": _tyre_deg_on_ref(deg_vals[c], ref_compound),
                "trend": {"pace": pace_trend.get(c, []), "quali": quali_trend.get(c, [])},
                "confidence": confidence(len(rounds_with_data.get(c, set())), total_rounds),
            }
        )

    return {"year": year, "rounds": rounds_meta, "constructors": rows}
