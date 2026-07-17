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
PU_GROUPS: tuple[PuGroup, ...] = (
    PuGroup("Mercedes", "Mercedes", ("Mercedes", "Alpine", "McLaren", "Williams")),
    PuGroup("Ferrari", "Ferrari", ("Ferrari", "Haas F1 Team", "Cadillac")),
    PuGroup("Red Bull", "Red Bull Racing", ("Red Bull Racing", "Racing Bulls")),
    PuGroup("Honda", "Aston Martin", ("Aston Martin",)),
    PuGroup("Audi", "Audi", ("Audi",)),
)

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


def rank_groups_best_to_worst(scatter: dict[str, list[list[float]]]) -> list[GroupMetrics]:
    """Every PU group with at least one team present in the scatter, ranked best-to-worst:
    punch (median accel 250-290 km/h, the band every group covers) descending, hold (>= 290
    km/h) as tiebreak. A group with no punch reading at all ranks last. Recomputed from
    whatever rounds are ingested, so the order shifts across the season as engines evolve."""
    metrics = [
        measure_group(g, scatter) for g in PU_GROUPS if any(scatter.get(t) for t in g.teams)
    ]

    def sort_key(m: GroupMetrics) -> tuple:
        return (m.punch is None, -(m.punch or 0.0), m.hold is None, -(m.hold or 0.0))

    return sorted(metrics, key=sort_key)
