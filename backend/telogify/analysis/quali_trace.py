"""Distance-grid resampling for qualifying telemetry comparisons ("The fight to pole"):
build one shared distance axis from the pole lap, then linearly interpolate any driver's
Speed/Throttle/Time onto it so traces line up point-for-point for a synchronized scrub and
for a pole-relative delta. Pure and unit-tested offline; no FastF1/DB imports.
"""

import numpy as np

GRID_STEP_M = 10.0  # ponytail: fixed step, no adaptive resolution. Tighten if a chart ever needs sub-10m precision.


def build_distance_grid(max_distance_m: float, step_m: float = GRID_STEP_M) -> list[float]:
    """0..max_distance_m, step_m apart, always including the final point exactly."""
    if max_distance_m <= 0:
        return [0.0]
    grid = list(np.arange(0.0, max_distance_m, step_m))
    grid.append(float(max_distance_m))
    return [round(v, 1) for v in grid]


def resample_to_grid(distance: list[float], values: list[float], grid: list[float]) -> list[float]:
    """Linear interpolation of `values` (sampled at `distance`) onto `grid`. Clamps outside
    the lap's own recorded range (np.interp's default edge behavior) rather than extrapolating.
    `distance` is assumed non-decreasing, as FastF1's per-lap Distance always is."""
    if not distance or not values:
        return [0.0] * len(grid)
    return np.interp(grid, distance, values).tolist()


def lap_relative_time_s(time_s: list[float]) -> list[float]:
    """Shift a lap's absolute Time-in-session samples so the lap itself starts at 0.0s."""
    if not time_s:
        return []
    t0 = time_s[0]
    return [t - t0 for t in time_s]


def delta_to_pole_s(time_on_grid: list[float], pole_time_on_grid: list[float]) -> list[float]:
    """Per-grid-point gap to the pole lap's time; zero everywhere when called with the pole's
    own time_on_grid. Both lists must be the same length (both resampled onto the same grid)."""
    return [t - p for t, p in zip(time_on_grid, pole_time_on_grid)]
