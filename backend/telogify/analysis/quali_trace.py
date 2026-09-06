"""Distance-aligned resampling for qualifying telemetry comparisons ("The fight to pole"):
build one shared nominal-distance axis, then resample every driver onto it BY LAP FRACTION --
each grid point samples a driver at the same fraction of that driver's OWN lap, not at the same
absolute meter reading.

Why fraction, not absolute distance: FastF1's `Distance` is `add_distance()`'s integral of
speed*dt, so two drivers' odometers disagree on how long the SAME physical lap is (the same
start/finish line reads e.g. 5821.8m for one car and 5840.8m for another). Aligning on absolute
meters therefore compares the two cars at slightly different fractions of the lap, which smears a
systematic bias across the whole delta trace and makes the finish-line delta NOT equal the real
lap-time gap -- confirmed on 2026 R9, where it made the runner-up appear ahead-on-cumulative-time
for ~80% of the lap and land at +0.018s instead of the true +0.175s. Fraction alignment pins both
cars to their own start/finish line at fraction 0 and 1, so the final delta is the true gap by
construction.

This is the same normalization FastF1's own `fastf1.utils.delta_time` uses -- it scales the
comparison lap's distance by `multiplier = ref.Distance.iat[-1] / comp.Distance.iat[-1]` (the
total-distance ratio) before interpolating, i.e. maps each lap onto a shared axis by lap fraction.
Their docs also flag distance-integrated delta as inherently approximate ("verify against sector
time differences"); the endpoint is the one point that is exact here (each lap sampled at its own
finish line), and it comes out equal to the official lap-time gap to sub-millisecond precision on
all 2026 data -- pinned by test_fraction_alignment_makes_final_delta_the_true_lap_time_gap. Pure
and unit-tested offline; no FastF1/DB imports.
"""

import statistics

import numpy as np

GRID_STEP_M = 10.0  # ponytail: fixed step, no adaptive resolution. Tighten if a chart ever needs sub-10m precision.


def build_distance_grid(max_distance_m: float, step_m: float = GRID_STEP_M) -> list[float]:
    """0..max_distance_m, step_m apart, always including the final point exactly. This is the
    shared NOMINAL-distance display axis; each driver is mapped onto it by fraction, so its own
    scale is just a representative lap length (see representative_max_distance_m)."""
    if max_distance_m <= 0:
        return [0.0]
    grid = list(np.arange(0.0, max_distance_m, step_m))
    grid.append(float(max_distance_m))
    return [round(v, 1) for v in grid]


MAX_PLAUSIBLE_DISTANCE_DEVIATION_FRAC = 0.025  # 2.5% of the field's median recorded lap length


def is_distance_plausible(
    distance_m: float,
    typical_distance_m: float,
    max_deviation_frac: float = MAX_PLAUSIBLE_DISTANCE_DEVIATION_FRAC,
) -> bool:
    """False when a lap's own recorded distance is implausibly far -- short OR long -- from the
    field's typical recorded distance for the same session. Almost certainly a telemetry
    integration glitch (e.g. a brief speed-channel dropout under-integrating FastF1's
    add_distance(), or a spurious spike over-integrating it), not a genuinely different racing
    line. Fraction alignment fixes the finish-line delta even for such a lap, but a LOCALIZED
    integration glitch still distorts the trace mid-lap (fraction-of-distance stops tracking
    fraction-of-track where the glitch sits), so a grossly-off lap is dropped from this chart
    entirely -- most importantly so it can't become the pole reference the whole comparison hangs
    on (2026 R3 Japan, pole recorded 5389m against a ~5770m field).

    The bound is a FRACTION of the lap length, not a flat metre count: add_distance() integrates
    speed*dt, so integration drift scales with lap duration and a flat cap is tightest on the
    longest circuits -- exactly backwards. Measured across 261 clean 2026 quali laps, abs
    deviation is p90 0.70%, p95 1.58%, p97 2.41%; genuine racing-line variance stays under ~1.9%
    (Monza pole 2026 R13, +110m / +1.92%, a verified-uniform stretch), while real glitches run
    2.7%+ (Suzuka pole 2026 R3, -6.6%). 2.5% sits at p97, keeping legitimate laps and dropping
    the corrupt ones. The driver's official lap time and result are untouched everywhere else in
    the product."""
    return abs(distance_m - typical_distance_m) <= max_deviation_frac * typical_distance_m


def representative_max_distance_m(driver_max_distances: list[float]) -> float:
    """Median of every driver's own recorded max distance this session, used as the nominal lap
    length for the shared display grid and as the reference the plausibility check compares
    against. The median shrugs off a single glitched lap; it takes a genuinely unreliable field
    for it to follow one outlier."""
    return statistics.median(driver_max_distances)


def fraction_aligned_query(grid: list[float], own_max_distance_m: float, nominal_max_distance_m: float) -> list[float]:
    """Map the shared nominal-distance `grid` onto THIS lap's own distance axis by lap fraction:
    a grid point at nominal distance g (fraction g/nominal_max of the nominal lap) becomes a query
    at the same fraction of this lap's OWN length. Feeding the result to resample_to_grid samples
    every driver at matching lap fractions, so the final grid point queries each lap at its own
    finish line and the delta there equals the real lap-time difference. `nominal_max` cancels
    into the fraction, so it only sets the display axis, never the alignment."""
    if nominal_max_distance_m <= 0:
        return list(grid)
    scale = own_max_distance_m / nominal_max_distance_m
    return [g * scale for g in grid]


def resample_to_grid(distance: list[float], values: list[float], query: list[float]) -> list[float]:
    """Linear interpolation of `values` (sampled at `distance`) onto the `query` distances. Clamps
    outside the lap's own recorded range (np.interp's default edge behavior); with fraction-aligned
    queries every point already lands within the lap's own 0..own_max range, so clamping is only a
    guard against floating-point overshoot at the exact endpoints. `distance` is assumed
    non-decreasing, as FastF1's per-lap Distance always is."""
    if not distance or not values:
        return [0.0] * len(query)
    return np.interp(query, distance, values).tolist()


def lap_relative_time_s(time_s: list[float]) -> list[float]:
    """Shift a lap's absolute Time-in-session samples so the lap itself starts at 0.0s."""
    if not time_s:
        return []
    t0 = time_s[0]
    return [t - t0 for t in time_s]


def resolve_pole_reference(
    drivers_with_laps: list[str],
    lap_times_s: dict[str, float],
    official_pole: str | None,
) -> tuple[str | None, str | None]:
    """(pole_driver, reference_driver) for "The fight to pole".

    pole_driver is the official qualifying P1 IF they have a usable trace lap here, else None --
    the chart must never relabel some other driver as pole just because the real pole sitter's
    telemetry was scrubbed (2026 R3 Japan: pole's lap recorded 5389m against a ~5770m field, so
    is_distance_plausible drops it; the runner-up is NOT the pole sitter).

    reference_driver is whose lap the delta-to-pole trace is measured against: the pole sitter
    when present, otherwise the fastest lap available so the panel still has a reference (the API
    tells the frontend to relabel that axis when pole_driver is None).
    """
    if not drivers_with_laps:
        return None, None
    pole = official_pole if official_pole in drivers_with_laps else None
    reference = pole or min(drivers_with_laps, key=lambda d: lap_times_s[d])
    return pole, reference


def delta_to_pole_s(time_on_grid: list[float], pole_time_on_grid: list[float]) -> list[float]:
    """Per-grid-point gap to the pole lap's time; zero everywhere when called with the pole's own
    time_on_grid. Both lists must be the same length (both resampled onto the same grid, by lap
    fraction), so the final point is each lap's finish line and the delta there is the true gap."""
    return [t - p for t, p in zip(time_on_grid, pole_time_on_grid)]
