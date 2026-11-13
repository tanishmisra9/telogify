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

from enum import Enum
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
# A car whose launch moment is more than this after the field's median did not start from the grid
# (a pit-lane starter leaves when the pit exit opens). Measured on 16 real 2026 races: grid starters
# launched at most +0.50 s after the median; pit-lane starters launched 6.5 to 12.2 s after it (or
# never inside the window). 3 s is 6x the largest grid delay and under half the smallest pit one. Used
# instead of lap 1's pit-out time, which OpenF1 sets for EVERY car (all 22 at Mexico 2026) and FastF1
# leaves empty for grid starters.
LATE_LAUNCH_S = 3.0
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


class Skip(str, Enum):
    """Why a driver is NOT on a race's start list. The one definition: the DB CHECK on
    `race_start_skip.reason` lists these same values, and the wording lives in `SKIP_LABEL`.
    Declared in the order the card lists them."""

    DID_NOT_START = "did_not_start"  # no lap 1 at all
    LATE_LAUNCH = "late_launch"  # left more than LATE_LAUNCH_S after the field (usually, not always, a pit-lane start)
    MOVING_AT_START = "moving_at_start"  # already rolling before lights out
    TOO_SLOW = "too_slow"  # 100 km/h not reached within MAX_WINDOW_S
    NO_200 = "no_200"  # timed, but no 0-200 time on a round where the field has them
    NO_DATA = "no_data"  # no usable speed trace around the start
    NO_COMMON_START = "no_common_start"  # round-level: the field did not launch together
    TOO_FEW_TIMED = "too_few_timed"  # round-level: too few cars timed to compare fairly


# Plain wording for each reason, served by the API so the frontend holds no copy. It states what
# the data shows and never a cause it cannot prove (no "safety car", no "crash").
SKIP_LABEL: dict[Skip, str] = {
    Skip.DID_NOT_START: "Did not start",
    # Measured facts only. "(pit-lane start)" was dropped: Bahrain 2026's late launchers were Russell
    # and Piastri, not pit-lane starters. "(stall or held up)" and "held up" were dropped as guesses.
    Skip.LATE_LAUNCH: "Left the grid more than 3 s after the field",
    Skip.MOVING_AT_START: "Already moving before the start",
    Skip.TOO_SLOW: "Took more than 8 s to reach 100 km/h",
    Skip.NO_200: "Did not reach 200 km/h within 8 s of the start",
    Skip.NO_DATA: "No speed data for the start",
    Skip.NO_COMMON_START: "Did not leave the grid together with the others",
    Skip.TOO_FEW_TIMED: "Left out because too few cars could be timed fairly",
}

# A round with no timing rows may be stored only when it carries one of these: they are findings
# about the race. Anything else with no rows (no car data, a crashed read) is a FAILED read and must
# never replace a good round's rows.
ROUND_LEVEL: frozenset[Skip] = frozenset({Skip.NO_COMMON_START, Skip.TOO_FEW_TIMED})

# Read-time fallback for a driver in the results with no recorded reason (a round extracted before
# reasons were stored), so a round is never claimed complete when it is not.
NO_READING = "no_reading"
NO_READING_LABEL = "No start reading recorded"

# The no-start card's one-line explanation, picked from the round's recorded reasons.
NO_START_SUMMARY = {
    Skip.NO_COMMON_START: "The cars did not all leave the grid at the same moment, so there is no shared start to time from.",
    Skip.TOO_FEW_TIMED: "Too few cars could be timed to compare starts fairly.",
}
NO_START_FALLBACK = "Start data could not be read for this race."


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


def grid_field(moments: dict[str, float]) -> tuple[float | None, dict[str, float]]:
    """(the shared start instant, the grid starters' launch moments). The instant is the median
    launch moment of the cars that started from the grid: a first median over every car finds the
    field, cars launching more than `LATE_LAUNCH_S` after it (pit-lane starters) are dropped, and
    the median is retaken over the rest. (None, {}) when too few cars remain."""
    if len(moments) < MIN_FIELD:
        return None, {}
    rough = median(moments.values())
    grid = {d: m for d, m in moments.items() if m - rough <= LATE_LAUNCH_S}
    if len(grid) < MIN_FIELD:
        return None, {}
    return median(grid.values()), grid


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


def launch_outcome(
    time_s: list[float], speed_kmh: list[float], lights_out_s: float
) -> tuple[Launch | None, Skip | None]:
    """`(launch, None)` when the car can be timed from `lights_out_s`, else `(None, why)`.
    `time_s` is ascending on the same axis as `lights_out_s` and must start before the car should
    already be sitting still; t_0_200 is None when the car never got there in time."""
    n = len(speed_kmh)
    if n < 3 or n != len(time_s):
        return None, Skip.NO_DATA
    settled = lights_out_s - PRE_STATIONARY_S
    if time_s[0] > settled:
        return None, Skip.NO_DATA  # the window doesn't show the car sitting still before lights out
    if any(v > STATIONARY_KMH for t, v in zip(time_s, speed_kmh) if t <= settled):
        return None, Skip.MOVING_AT_START  # rolling before lights out (pit exit, creep, rolling start)
    after = next((i for i, t in enumerate(time_s) if t > lights_out_s), None)
    if after is None:
        return None, Skip.NO_DATA
    t100 = _cross(time_s, speed_kmh, after, 100.0)
    if t100 is None or t100 - lights_out_s > MAX_WINDOW_S:
        return None, Skip.TOO_SLOW
    t200 = _cross(time_s, speed_kmh, after, 200.0)
    if t200 is not None and t200 - lights_out_s > MAX_WINDOW_S:
        t200 = None
    return (t100 - lights_out_s, (None if t200 is None else t200 - lights_out_s)), None


def launch_times(time_s: list[float], speed_kmh: list[float], lights_out_s: float) -> Launch | None:
    """(t_0_100, t_0_200) in seconds after `lights_out_s`, or None when the start can't be timed
    (`launch_outcome` says why)."""
    return launch_outcome(time_s, speed_kmh, lights_out_s)[0]


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
