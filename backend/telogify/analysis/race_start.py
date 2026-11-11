"""Standing-start acceleration times (0-100 and 0-200 km/h) from lap-1 car telemetry. Pure (no
FastF1/DB) so it is unit-tested offline.

Every time is measured from ONE shared instant for the whole field ("lights out"), not from each
car's own first movement: reaction time is part of a start, and FastF1's 0.24-0.36 s sample
spacing is too coarse to resolve a per-car launch moment cleanly (per-car detection matched the
reference chart for 16 of 21 drivers; one shared instant matched 21 of 21).

Lap 1's `LapStartDate` is NOT a usable lights-out marker: it sat ~0.4 s before the Spanish GP
field's launch but ~1.4 s AFTER the Austrian GP field's. So the instant is derived from the
field's own speed traces each race: each car's launch moment is its first climb off the grid
extrapolated back to 0 km/h (sub-sample resolution), and the field's median launch moment is the
shared start instant. No fitted constant: checked against the fdataanalysis chart for the 2026
Spanish GP, this reproduces all 21 of their drivers' times at one decimal, with zero mean bias.

Three figures per car, each shown for a round only when most of the field has it (`covers_field`):
0-100 km/h time (every standing start reaches it), 0-200 km/h time (not at Baku/Monaco, where the
first braking zone comes first, and a chart of the few that got there would be a biased subset),
and `speed_at_distance`: km/h after `SPEED_DISTANCE_M` metres. That last one is measured from the
car's OWN first movement, so unlike the times it carries no reaction time: it is pure launch and
traction, and every car is compared over the same distance whatever its grid slot.

A figure is None, never a guess, when a car's start can't be read cleanly: not stationary just
before lights out (pit-lane start, rolling or safety-car start), too slow (`MAX_WINDOW_S`), or
its speed fell before the distance was covered (lifting or braking behind traffic).
"""

from statistics import median

import numpy as np

# Speed at or below this counts as stationary (FastF1 reports 0 km/h on the grid; a little slack
# absorbs integer-speed quantisation).
STATIONARY_KMH = 2.0
# A car must be stationary this long before lights out. Early reactors launch a few tenths
# before the median instant, so this is a margin, not "stationary at lights out".
PRE_STATIONARY_S = 0.6
# A 200 km/h mark later than this after lights out is not a launch time. A heuristic, not a
# measured boundary: 2026 times reach ~7.7-8.0 s in a few races (Australia, China, Japan), mostly
# cars lifting behind others into turn 1, so bars past ~6 s can include traffic.
MAX_WINDOW_S = 8.0
# Speed band whose straight-line fit gives a car's launch moment: clear of the grid-creep
# quantisation below it and of the gear-change flattening above it.
_FIT_LOW_KMH, _FIT_HIGH_KMH = 10.0, 60.0
# Too few readable cars and the field's median launch is not trustworthy.
MIN_FIELD = 5
# Share of the readable-start cars that must have a figure for that figure to be shown.
MIN_COVERAGE = 0.7
# Distance over which launch speed is read. One universal value so weekends compare. A
# heuristic, not a published standard: at 75 m far fewer cars have lifted for traffic than at 100 m
# (Monaco 20/21 vs 18/21 on 2026 data), while every car is still well into its launch.
SPEED_DISTANCE_M = 75.0
# A car whose speed falls this far below its running maximum before the distance is covered has
# lifted or braked, so its launch is not what the figure is meant to show. NOT the Brake channel:
# that flag reads true under 70-100% throttle on some launches (China, Japan 2026).
SPEED_DROP_KMH = 3.0

# (t_0_100, t_0_200 or None) in seconds after lights out.
Launch = tuple[float, float | None]


def _first_move(speed_kmh: list[float]) -> int | None:
    return next((i for i, v in enumerate(speed_kmh) if v > STATIONARY_KMH), None)


def launch_moment(time_s: list[float], speed_kmh: list[float]) -> float | None:
    """When this car left the grid: its first rise through 10-60 km/h, fitted as a line and
    extrapolated back to 0 km/h. None unless it sat stationary first and rose cleanly."""
    n = len(speed_kmh)
    if n < 5 or n != len(time_s):
        return None
    first = _first_move(speed_kmh)
    if first is None or first < 2:  # needs a stationary lead-in, not already moving
        return None
    # Only the first climb off the grid: later samples in the same speed band (braking into
    # turn 1, a lift) are a different event and would wreck the fit.
    pts: list[tuple[float, float]] = []
    for t_i, v_i in zip(time_s[first - 1 :], speed_kmh[first - 1 :]):
        if v_i > _FIT_HIGH_KMH:
            break
        if v_i >= _FIT_LOW_KMH:
            pts.append((t_i, v_i))
    if len(pts) < 3:
        return None
    t = np.array([p[0] for p in pts])
    v = np.array([p[1] for p in pts])
    slope, intercept = np.polyfit(t, v, 1)
    if slope <= 0:
        return None
    return float(-intercept / slope)


def field_lights_out(moments: list[float]) -> float | None:
    """The shared start instant: the median of every readable car's launch moment."""
    if len(moments) < MIN_FIELD:
        return None
    return median(moments)


def covers_field(n_timed: int, n_readable: int) -> bool:
    """True when enough of the readable-start cars were timed to represent the field."""
    return n_timed >= MIN_FIELD and n_timed >= MIN_COVERAGE * n_readable


def _cross(time_s: list[float], speed: list[float], start: int, level: float) -> float | None:
    """Interpolated time at which speed first rises through `level`, scanning from index `start`."""
    for i in range(max(start, 1), len(speed)):
        if speed[i - 1] < level <= speed[i]:
            span = speed[i] - speed[i - 1]
            return time_s[i - 1] + (time_s[i] - time_s[i - 1]) * (level - speed[i - 1]) / span
    return None


def launch_times(time_s: list[float], speed_kmh: list[float], lights_out_s: float) -> Launch | None:
    """(t_0_100, t_0_200) in seconds after `lights_out_s`; t_0_200 is None when the car never got
    there in time (it still has a 0-100 time). `time_s` is ascending on the same axis as
    `lights_out_s` and must start before the car should already be sitting still."""
    n = len(speed_kmh)
    if n < 3 or n != len(time_s):
        return None
    settled = lights_out_s - PRE_STATIONARY_S
    if time_s[0] > settled:
        return None  # window doesn't show the car sitting still before lights out
    if any(v > STATIONARY_KMH for t, v in zip(time_s, speed_kmh) if t <= settled):
        return None  # moving before lights out: rolling / safety-car start, or a pit-lane car
    after = next((i for i, t in enumerate(time_s) if t > lights_out_s), None)
    if after is None:
        return None
    t100 = _cross(time_s, speed_kmh, after, 100.0)
    if t100 is None or t100 - lights_out_s > MAX_WINDOW_S:
        return None
    t200 = _cross(time_s, speed_kmh, after, 200.0)
    if t200 is not None and t200 - lights_out_s > MAX_WINDOW_S:
        t200 = None
    return t100 - lights_out_s, (None if t200 is None else t200 - lights_out_s)


def speed_at_distance(
    time_s: list[float], speed_kmh: list[float], distance_m: float = SPEED_DISTANCE_M
) -> float | None:
    """Speed in km/h once the car has covered `distance_m` from its own launch, distance being the
    trapezoid integral of the speed trace. None when the car lifted or braked first, the trace
    ends first, or its launch can't be read."""
    t0 = launch_moment(time_s, speed_kmh)
    first = _first_move(speed_kmh)
    if t0 is None or first is None:
        return None
    # From t0 (0 km/h) to the first moving sample, speed rises linearly.
    dist = 0.5 * (speed_kmh[first] / 3.6) * max(time_s[first] - t0, 0.0)
    peak = speed_kmh[first]
    if dist >= distance_m:
        return speed_kmh[first]
    for i in range(first + 1, len(speed_kmh)):
        v0, v1, dt = speed_kmh[i - 1], speed_kmh[i], time_s[i] - time_s[i - 1]
        peak = max(peak, v1)
        if peak - v1 > SPEED_DROP_KMH:
            return None  # lifted or braked before the distance was covered
        step = (v0 + v1) / 2 / 3.6 * dt
        if dist + step >= distance_m:
            # Solve for the point inside this sample gap where the distance is reached, with
            # speed linear between the two samples.
            a = (v1 - v0) / 3.6 / dt if dt > 0 else 0.0  # m/s^2
            need = distance_m - dist
            v0_ms = v0 / 3.6
            if abs(a) < 1e-9:
                return v0 if v0_ms > 0 else None
            disc = v0_ms * v0_ms + 2 * a * need
            if disc < 0:
                return None
            return float((v0_ms**2 + 2 * a * need) ** 0.5 * 3.6)
        dist += step
    return None
