"""Clean-lap filtering and corner segmentation.

`is_clean_lap` and `corner_windows` are pure so they can be unit-tested offline;
the FastF1 DataFrame plumbing wraps them.
"""

from dataclasses import dataclass

import pandas as pd

# ponytail: track-temp deviation (C) that flags a non-representative lap. Tune knob.
TEMP_SWING_C = 5.0
# ponytail: half-width (m) of the per-corner distance window. Widen on long corners.
CORNER_HALF_WINDOW_M = 75.0


@dataclass(frozen=True)
class Corner:
    number: int
    distance: float


def is_clean_lap(
    *,
    is_accurate: bool,
    deleted: bool,
    in_out_lap: bool,
    track_status: str,
    rainfall: bool,
    track_temp: float | None,
    median_track_temp: float | None,
) -> bool:
    """A lap usable for telemetry comparison: green-flag, dry, in-rhythm, accurately timed."""
    if not is_accurate or deleted or in_out_lap or rainfall:
        return False
    # TrackStatus '1' is all-clear for the whole lap; anything else means yellow/SC/VSC/red.
    if str(track_status) != "1":
        return False
    if median_track_temp is not None and track_temp is not None:
        if abs(track_temp - median_track_temp) > TEMP_SWING_C:
            return False
    return True


def _f(value) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(f) else f


def select_clean_laps(session) -> "pd.DataFrame":
    """Filter a loaded FastF1 session's laps down to clean laps."""
    laps = session.laps
    if len(laps) == 0:
        return laps

    weather = laps.get_weather_data().reset_index(drop=True)
    laps_reset = laps.reset_index(drop=True)
    median_temp = _f(weather["TrackTemp"].median()) if "TrackTemp" in weather else None

    keep = []
    for i in range(len(laps_reset)):
        lap = laps_reset.iloc[i]
        w = weather.iloc[i]
        in_out = pd.notna(lap.get("PitInTime")) or pd.notna(lap.get("PitOutTime"))
        keep.append(
            is_clean_lap(
                is_accurate=bool(lap.get("IsAccurate", False)),
                deleted=bool(lap.get("Deleted", False)),
                in_out_lap=bool(in_out),
                track_status=lap.get("TrackStatus", ""),
                rainfall=bool(w.get("Rainfall", False)),
                track_temp=_f(w.get("TrackTemp")),
                median_track_temp=median_temp,
            )
        )
    return laps[pd.Series(keep, index=laps.index)]


def clean_lap_counts(session) -> dict[str, int]:
    """Driver -> number of clean laps in the session."""
    laps = select_clean_laps(session)
    if len(laps) == 0:
        return {}
    return {d: int(n) for d, n in laps.groupby("Driver").size().items()}


def get_corners(session) -> list[Corner]:
    """Corner number + lap distance from FastF1 circuit info.

    FastF1 projects corner positions onto `laps.pick_fastest()`; on circuits like Monaco that
    reference lap's telemetry can fail to merge (tunnel position gaps), raising deep inside
    FastF1. Fall back to a reference lap whose telemetry merges cleanly, then to no corners.
    """
    try:
        info = session.get_circuit_info()
    except Exception:
        info = _circuit_info_resilient(session)
    if info is None or getattr(info, "corners", None) is None or len(info.corners) == 0:
        return []
    return [Corner(int(r["Number"]), float(r["Distance"])) for _, r in info.corners.iterrows()]


def _circuit_info_resilient(session):
    """Rebuild circuit info using the first lap whose telemetry merges cleanly as the distance
    reference, instead of FastF1's default (and here failing) pick_fastest()."""
    try:
        from fastf1.mvapi import get_circuit_info as _mv_circuit_info

        circuit_key = session.session_info["Meeting"]["Circuit"]["Key"]
        year = session.event.year
    except Exception:
        return None
    try:
        laps = session.laps.pick_accurate()
    except Exception:
        laps = session.laps
    attempts = 0
    for _, lap in laps.iterlaps():
        if attempts >= 8:  # bound the cost if many laps have unmergeable telemetry
            break
        attempts += 1
        try:
            info = _mv_circuit_info(year=year, circuit_key=circuit_key)
            info.add_marker_distance(reference_lap=lap)
            if info.corners is not None and len(info.corners):
                return info
        except Exception:
            continue
    return None


def corner_windows(
    corners: list[Corner], half_window_m: float = CORNER_HALF_WINDOW_M
) -> list[tuple[int, float, float]]:
    """[(corner_number, distance_start, distance_end)] windows for telemetry slicing."""
    return [(c.number, c.distance - half_window_m, c.distance + half_window_m) for c in corners]
