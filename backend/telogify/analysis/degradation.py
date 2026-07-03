"""Tyre degradation: fuel-corrected lap time vs tyre age, per team and compound.

The signal is the slope, not absolute pace: how many seconds a lap a team loses for every
extra lap on that tyre. Fuel correction happens upstream (ingest/stints.py); this module
only regresses already fuel-corrected times against tyre age, so the slope is not
contaminated by the lightening fuel load. The slope is estimated with the Theil-Sen
estimator (median of pairwise slopes), not ordinary least squares: race stints are small,
heavy-tailed samples where one traffic-compromised or lock-up lap would dominate an OLS fit
(OLS breakdown point 0 vs Theil-Sen ~29%). Both are pure Python, no numpy dependency.

Only the what (slope, cumulative cost) and the strategic consequence (stop count) are
computed here. A physical cause (e.g. rear-tyre heat) is never asserted; the caller may
attach one only when a retrievable signal (e.g. track temperature) supports it.
"""

from collections import defaultdict
from dataclasses import dataclass
from statistics import median

# A team-compound's slope is flagged when it is at least this many times the field's
# median slope for that compound (the brief's Ferrari example was 2x; this is a broader net).
FLAG_MULTIPLIER = 1.5
REFERENCE_AGE_LAPS = 13  # cumulative cost is reported "by lap N" using this reference
MIN_LAPS_FOR_FIT = 5  # a handful of points can fit a "perfect" line through noise


@dataclass
class DegradationFit:
    constructor: str
    compound: str
    slope_s_per_lap: float
    intercept_s: float
    cost_at_reference_s: float  # slope * REFERENCE_AGE_LAPS: cumulative cost by that age
    n_laps: int
    flagged: bool = False


def least_squares_fit(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    """(slope, intercept) of ys regressed on xs by OLS, or None with fewer than 2 points or no
    variance in xs (can't fit a line through a single tyre age). Kept as a reference/comparison;
    fit_group uses the outlier-robust theil_sen_fit instead."""
    n = len(xs)
    if n < 2:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    var_x = sum((x - mean_x) ** 2 for x in xs)
    if var_x == 0:
        return None
    cov_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = cov_xy / var_x
    intercept = mean_y - slope * mean_x
    return slope, intercept


def theil_sen_fit(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    """(slope, intercept) via the Theil-Sen estimator: slope = median of the slopes of every
    pair of points with distinct x; intercept = median(y - slope*x). Robust to outlier laps
    (breakdown point ~29% vs 0 for OLS). None with fewer than 2 points or no distinct-x pair.
    O(n^2) in the number of laps, which is fine at stint scale (tens of laps)."""
    n = len(xs)
    if n < 2:
        return None
    slopes = [
        (ys[j] - ys[i]) / (xs[j] - xs[i])
        for i in range(n)
        for j in range(i + 1, n)
        if xs[j] != xs[i]
    ]
    if not slopes:
        return None
    slope = median(slopes)
    intercept = median([y - slope * x for x, y in zip(xs, ys)])
    return slope, intercept


def fit_group(
    constructor: str,
    compound: str,
    ages: list[float],
    times: list[float],
    *,
    reference_age: int = REFERENCE_AGE_LAPS,
    min_laps: int = MIN_LAPS_FOR_FIT,
) -> DegradationFit | None:
    """ages/times: fuel-corrected lap time paired with tyre age, same length, same order.
    Below `min_laps` points, a line fits perfectly through noise and isn't a real slope.
    """
    if len(ages) < min_laps:
        return None
    fit = theil_sen_fit(ages, times)
    if fit is None:
        return None
    slope, intercept = fit
    return DegradationFit(
        constructor=constructor,
        compound=compound,
        slope_s_per_lap=slope,
        intercept_s=intercept,
        cost_at_reference_s=slope * reference_age,
        n_laps=len(ages),
    )


def fit_all_groups(rows: list[dict], *, reference_age: int = REFERENCE_AGE_LAPS) -> list[DegradationFit]:
    """rows: dicts with constructor, compound, tyre_age, lap_time_s (one row per kept lap).

    Fits one slope per (constructor, compound), then flags any fit whose slope is at
    least FLAG_MULTIPLIER times that compound's field-median slope (positive slopes only;
    a flat or negative slope means no real wear signal to compare against).
    """
    grouped: dict[tuple[str, str], tuple[list[float], list[float]]] = defaultdict(lambda: ([], []))
    for r in rows:
        if r.get("tyre_age") is None or r.get("lap_time_s") is None:
            continue
        ages, times = grouped[(r["constructor"], r["compound"])]
        ages.append(r["tyre_age"])
        times.append(r["lap_time_s"])

    fits = []
    for (constructor, compound), (ages, times) in grouped.items():
        fit = fit_group(constructor, compound, ages, times, reference_age=reference_age)
        if fit is not None:
            fits.append(fit)

    by_compound: dict[str, list[float]] = defaultdict(list)
    for fit in fits:
        if fit.slope_s_per_lap > 0:
            by_compound[fit.compound].append(fit.slope_s_per_lap)
    field_median = {compound: median(slopes) for compound, slopes in by_compound.items()}

    for fit in fits:
        ref = field_median.get(fit.compound)
        if ref and ref > 0 and fit.slope_s_per_lap >= FLAG_MULTIPLIER * ref:
            fit.flagged = True
    return fits
