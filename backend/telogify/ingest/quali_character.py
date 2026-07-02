"""Qualifying car-character extraction.

For each driver's fastest qualifying lap, read one consistent telemetry trace and derive
lap time, top speed, minimum speed, full-throttle percentage, and a min-speed-per-corner
map together, so every number describes the same lap rather than being pooled from
different laps/compounds the way `Fingerprint` (car-vs-driver attribution) is. Per-corner
speeds are kept as a map (not reduced to a single "fastest corner" here) because which
corner counts as "the fastest corner" for the car-character table is a field-relative
choice made once across the compared teams (see analysis/quali_character.py), not a
per-driver personal best.

Lap selection here deliberately does NOT reuse `segment.select_clean_laps`: that filter
requires TrackStatus to be a clean "1" for the *entire* lap, which is right for pooling
many laps into a corner/straight-line average, but wrong for picking a single fastest
lap. FastF1 sometimes tags a lap's TrackStatus with a caution thrown right as the lap
ends (e.g. right after the driver crosses the line), producing a compound status like
"12" even though the flying lap itself was clean and it stood as the official qualifying
time. Excluding it here would silently drop a real pole lap from the comparison. See
`select_representative_laps`.

`lap_character` is pure and unit-tested offline.
"""

from dataclasses import dataclass

import pandas as pd
from sqlmodel import Session as DBSession
from sqlmodel import delete, select

from telogify.ingest.loader import WeekendData
from telogify.ingest.segment import corner_windows, get_corners
from telogify.models import QualiCharacter, Session

FULL_THROTTLE_PCT = 99.0  # throttle reading (0-100) counted as "full throttle"


def is_representative_lap(
    *, is_accurate: bool, deleted: bool, in_out_lap: bool, rainfall: bool
) -> bool:
    """A lap that officially counts and is fit for a single-lap telemetry read: accurate,
    not deleted, not an in/out lap, dry. Track status is intentionally not checked (see
    module docstring): that check belongs to pooled multi-lap comparisons, not picking
    one driver's fastest lap.
    """
    return is_accurate and not deleted and not in_out_lap and not rainfall


def select_representative_laps(session) -> "pd.DataFrame":
    """Filter a loaded FastF1 session's laps down to laps usable for a single fastest-lap
    read per driver (see module docstring for why this differs from
    `segment.select_clean_laps`)."""
    laps = session.laps
    if len(laps) == 0:
        return laps

    weather = laps.get_weather_data().reset_index(drop=True)
    laps_reset = laps.reset_index(drop=True)

    keep = []
    for i in range(len(laps_reset)):
        lap = laps_reset.iloc[i]
        w = weather.iloc[i]
        in_out = pd.notna(lap.get("PitInTime")) or pd.notna(lap.get("PitOutTime"))
        keep.append(
            is_representative_lap(
                is_accurate=bool(lap.get("IsAccurate", False)),
                deleted=bool(lap.get("Deleted", False)),
                in_out_lap=bool(in_out),
                rainfall=bool(w.get("Rainfall", False)),
            )
        )
    return laps[pd.Series(keep, index=laps.index)]


@dataclass(frozen=True)
class LapCharacter:
    top_speed_kmh: float
    min_speed_kmh: float
    corner_speeds_kmh: dict[int, float]  # corner_number -> min speed in that corner's window
    full_throttle_pct: float


def full_throttle_fraction(throttle: list[float], threshold: float = FULL_THROTTLE_PCT) -> float:
    if not throttle:
        return 0.0
    at_full = sum(1 for t in throttle if t >= threshold)
    return at_full / len(throttle)


def _min_in_window(distance: list[float], speed: list[float], lo: float, hi: float) -> float | None:
    vals = [speed[i] for i in range(len(distance)) if lo <= distance[i] <= hi]
    return min(vals) if vals else None


def corner_min_speeds(
    distance: list[float], speed: list[float], windows: list[tuple[int, float, float]]
) -> dict[int, float]:
    """Each corner's minimum speed on this lap, keyed by corner number."""
    out = {}
    for corner_number, lo, hi in windows:
        m = _min_in_window(distance, speed, lo, hi)
        if m is not None:
            out[corner_number] = m
    return out


def lap_character(
    distance: list[float],
    speed: list[float],
    throttle: list[float],
    windows: list[tuple[int, float, float]],
) -> LapCharacter | None:
    if not distance or not speed:
        return None
    return LapCharacter(
        top_speed_kmh=max(speed),
        min_speed_kmh=min(speed),
        corner_speeds_kmh=corner_min_speeds(distance, speed, windows),
        full_throttle_pct=full_throttle_fraction(throttle),
    )


def extract_quali_character(session) -> dict[str, tuple[str | None, float, LapCharacter]]:
    """driver -> (constructor, lap_time_s, LapCharacter), from each driver's fastest
    representative lap (see module docstring for the lap-selection rule)."""
    reps = select_representative_laps(session)
    if len(reps) == 0:
        return {}
    windows = corner_windows(get_corners(session))

    out: dict[str, tuple[str | None, float, LapCharacter]] = {}
    for driver in reps["Driver"].unique():
        drv_laps = reps[reps["Driver"] == driver]
        lap = drv_laps.loc[drv_laps["LapTime"].idxmin()]
        try:
            tel = lap.get_telemetry()
        except Exception:
            continue
        if "Distance" not in tel or len(tel) == 0:
            continue
        char = lap_character(
            tel["Distance"].tolist(),
            tel["Speed"].tolist(),
            tel["Throttle"].tolist(),
            windows,
        )
        if char is None:
            continue
        constructor = lap.get("Team")
        out[driver] = (constructor, lap["LapTime"].total_seconds(), char)
    return out


def store_quali_character(data: WeekendData, db: DBSession) -> None:
    for code, session in data.sessions.items():
        if code not in ("Q", "SQ"):
            continue
        row = db.exec(
            select(Session).where(
                Session.weekend_id == data.weekend.id, Session.session_type == code
            )
        ).first()
        if row is None:
            continue
        db.exec(delete(QualiCharacter).where(QualiCharacter.session_id == row.id))
        for driver, (constructor, lap_time_s, char) in extract_quali_character(session).items():
            db.add(
                QualiCharacter(
                    session_id=row.id,
                    driver=driver,
                    constructor=constructor,
                    lap_time_s=lap_time_s,
                    top_speed_kmh=char.top_speed_kmh,
                    min_speed_kmh=char.min_speed_kmh,
                    full_throttle_pct=char.full_throttle_pct,
                    corner_speeds_json={str(k): v for k, v in char.corner_speeds_kmh.items()},
                )
            )
    db.commit()
