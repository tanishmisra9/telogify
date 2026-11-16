"""Season deployment: power-unit acceleration character (punch/hold/fade) from the pooled
season accel scatter (season.py's build_season_accel_scatter), plus the 2026 team -> power-unit
manufacturer supply map.

Ported from the frontend's deprecated deploymentInsights.ts/seasonAccel.ts templates so an LLM
writer (agent/season_deployment.py) can turn these metrics into prose, instead of a fixed
template. Metric design is unchanged: full-throttle no-brake samples live almost entirely above
~220 km/h, and no PU group's binned median actually crosses zero mid-range, so what separates
the groups is (a) how hard they accelerate through the 250-290 km/h meat of the range every
group covers ("punch": more deployment vs more harvesting), (b) what's left past 290 km/h
("hold": the clipping story), and (c) how far each falls from punch to hold ("fade").

Pure functions only; no DB imports here so the module is unit-testable offline.
"""

from dataclasses import dataclass
from statistics import median


@dataclass(frozen=True)
class PuGroup:
    name: str  # power-unit manufacturer, e.g. "Mercedes"
    works_team: str  # team whose color marks the row
    teams: tuple[str, ...]  # constructors running this PU, 2026


# 2026 power unit supply map. Season-specific by nature, like the hardcoded frontend team colors.
# The season this team -> power-unit supply map describes. It is NOT valid for other years (Red Bull
# ran Honda in 2025), so anything keyed on it must check the year.
PU_GROUPS_YEAR = 2026
PU_GROUPS: tuple[PuGroup, ...] = (
    PuGroup("Mercedes", "Mercedes", ("Mercedes", "Alpine", "McLaren", "Williams")),
    PuGroup("Ferrari", "Ferrari", ("Ferrari", "Haas F1 Team", "Cadillac")),
    PuGroup("Red Bull", "Red Bull Racing", ("Red Bull Racing", "Racing Bulls")),
    PuGroup("Honda", "Aston Martin", ("Aston Martin",)),
    PuGroup("Audi", "Audi", ("Audi",)),
)

def pu_map_applies(year: int, teams: set[str]) -> bool:
    """True when the supply map describes `year` AND covers every team in `teams` (a partial map
    would silently drop cars from a power-unit view). The one place that decision lives."""
    return year == PU_GROUPS_YEAR and teams <= {t for g in PU_GROUPS for t in g.teams}


MIN_BIN_N = 5  # a bin's median is meaningless on fewer samples
MIN_BINS_PER_BAND = 2  # a band needs at least two solid bins to be a read
MID_LO = 250.0  # "punch" band: the shared meat of every group's coverage
MID_HI = 290.0  # "hold" band: everything past this, where deployment running out shows as accel ~0
BIN_WIDTH_KMH = 10.0


@dataclass
class AccelBin:
    speed_mid: float
    median_accel: float
    n: int


def bin_by_speed(
    points: list[tuple[float, float]], bin_width_kmh: float = BIN_WIDTH_KMH
) -> list[AccelBin]:
    """Bin (speed, accel) points by speed and take the median accel per bin, so a season's worth
    of raw points reads as one legible curve instead of an unreadable cloud."""
    buckets: dict[float, list[float]] = {}
    for speed, accel in points:
        bucket = (speed // bin_width_kmh) * bin_width_kmh
        buckets.setdefault(bucket, []).append(accel)
    bins = [
        AccelBin(speed_mid=bucket + bin_width_kmh / 2, median_accel=median(accels), n=len(accels))
        for bucket, accels in buckets.items()
    ]
    return sorted(bins, key=lambda b: b.speed_mid)


@dataclass
class GroupMetrics:
    group: PuGroup
    teams: list[str]  # members actually present in the scatter
    punch: float | None  # median of bin medians, 250-290 km/h
    hold: float | None  # median of bin medians, >= 290 km/h
    fade: float | None  # punch - hold


def measure_group(group: PuGroup, scatter: dict[str, list[list[float]]]) -> GroupMetrics:
    teams = [t for t in group.teams if scatter.get(t)]
    pooled = [(sp, ac) for t in teams for sp, ac in scatter.get(t, [])]
    bins = [b for b in bin_by_speed(pooled) if b.n >= MIN_BIN_N]
    mid = [b.median_accel for b in bins if MID_LO <= b.speed_mid < MID_HI]
    top = [b.median_accel for b in bins if b.speed_mid >= MID_HI]
    punch = median(mid) if len(mid) >= MIN_BINS_PER_BAND else None
    hold = median(top) if len(top) >= MIN_BINS_PER_BAND else None
    fade = punch - hold if punch is not None and hold is not None else None
    return GroupMetrics(group=group, teams=teams, punch=punch, hold=hold, fade=fade)


def _package_score(m: GroupMetrics) -> float | None:
    """Whole-band package strength: the mean of punch and hold when both bands were measured,
    falling back to whichever one is known. None only when neither band could be measured.
    Ranking on punch alone (the previous logic) rewarded whoever pulls hardest through the
    250-290 km/h band and used hold only to break an exact tie, which in practice never
    happens with real floats, i.e. it was a punch-only ranking. Averaging the two means a car
    that pulls hard early but fades hard late no longer outranks one that holds its shove deep
    into the range, so both "how hard" and "how long" count toward the overall package."""
    vals = [v for v in (m.punch, m.hold) if v is not None]
    return sum(vals) / len(vals) if vals else None


def rank_groups_best_to_worst(scatter: dict[str, list[list[float]]]) -> list[GroupMetrics]:
    """Every PU group with at least one team present in the scatter, ranked best-to-worst by
    _package_score (mean of punch and hold). A group with no reading in either band ranks
    last. Recomputed from whatever rounds are ingested, so the order shifts across the season
    as engines evolve."""
    metrics = [
        measure_group(g, scatter) for g in PU_GROUPS if any(scatter.get(t) for t in g.teams)
    ]

    def sort_key(m: GroupMetrics) -> tuple:
        score = _package_score(m)
        return (score is None, -(score or 0.0))

    return sorted(metrics, key=sort_key)


def package_form(
    by_round: dict[int, dict[str, list[list[float]]]], current_round: int
) -> dict[str, dict]:
    """Rank movement per power unit from its per-round package score, same meaning as the other Trends
    arrows (places gained on recent form versus the whole season; None below MIN_ROUNDS_FOR_FORM).

    A raw package score is NOT comparable across rounds (a track with no bins past MID_HI scores on punch
    alone, which reads higher), so each round's value is the gap to that round's best package, counted only
    for a group whose measured bands match the best group's. Lower is better, as form_movement expects."""
    from telogify.analysis.season import form_movement  # local: season.py is the heavier module

    values: dict[str, list[tuple[int, float]]] = {}
    for rnd, scatter in by_round.items():
        scored = [
            (m, _package_score(m))
            for m in (measure_group(g, scatter) for g in PU_GROUPS if any(scatter.get(t) for t in g.teams))
        ]
        scored = [(m, sc) for m, sc in scored if sc is not None]
        if not scored:
            continue
        best_m, best = max(scored, key=lambda t: t[1])
        sig = (best_m.punch is not None, best_m.hold is not None)
        for m, sc in scored:
            if (m.punch is not None, m.hold is not None) == sig:
                values.setdefault(m.group.name, []).append((rnd, best - sc))
    return form_movement(values, current_round)


def build_ranking(
    scatter: dict[str, list[list[float]]], by_round: dict[int, dict[str, list[list[float]]]]
) -> list[dict]:
    """The Deployment ranking table: every power unit ranked best to worst on the season-pooled package
    score (the same order the verdict panels use), its gap to the best, and the form arrow. `gap` and
    `score` are m/s^2; None when neither band could be measured."""
    form = package_form(by_round, max(by_round)) if by_round else {}
    ranked = rank_groups_best_to_worst(scatter)
    scores = [_package_score(m) for m in ranked]
    best = max((s for s in scores if s is not None), default=None)
    # A score built from one band (the other too thin to read) is not like-for-like with the best group's two-band
    # mean: it keeps its rank but shows no gap, rather than a misleading m/s^2 figure.
    best_sig = next(((m.punch is not None, m.hold is not None) for m, sc in zip(ranked, scores) if sc == best), None)
    return [
        {
            "pu": m.group.name,
            "works_team": m.group.works_team,
            "rank": i + 1,
            "score": sc,
            "gap": None
            if sc is None or best is None or (m.punch is not None, m.hold is not None) != best_sig
            else best - sc,
            "form_places": form.get(m.group.name, {}).get("form_places"),
            "rank_weighted": form.get(m.group.name, {}).get("rank_weighted"),
            "rank_flat": form.get(m.group.name, {}).get("rank_flat"),
        }
        for i, (m, sc) in enumerate(zip(ranked, scores))
    ]
