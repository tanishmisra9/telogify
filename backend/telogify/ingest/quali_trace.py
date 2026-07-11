"""Distance-aligned qualifying telemetry traces for "The fight to pole": per driver, from the
fastest representative Q lap, speed/throttle/delta-to-pole resampled onto one shared distance
grid so every driver's trace lines up point-for-point.

Reuses the same representative-lap selection as quali_character/deployment (fastest
representative lap per driver, no pooled multi-lap TrackStatus gate). MAIN Qualifying only
(session type "Q") -- Sprint Qualifying is deliberately excluded, unlike deployment.py's
Q/SQ-agnostic extraction, because "the fight to pole" is specifically about the session that
decides pole. Stored per driver, idempotently, for every driver with a usable lap -- not just
the eventual top two -- so a future compare-any-two (or add-a-driver) UI needs no re-ingest.
"""

from sqlmodel import Session as DBSession
from sqlmodel import delete, select

from telogify.analysis.quali_trace import (
    build_distance_grid,
    delta_to_pole_s,
    lap_relative_time_s,
    resample_to_grid,
)
from telogify.ingest.loader import WeekendData
from telogify.ingest.quali_character import select_representative_laps
from telogify.ingest.segment import get_corners
from telogify.models import QualiTrace, Session


def extract_quali_traces(session) -> tuple[dict[str, dict], list[float]]:
    """driver -> {constructor, lap_time_s, is_pole, speed_kmh, throttle_pct, delta_s}, plus the
    shared distance grid (built from the pole lap's own max distance). Empty ({}, []) when no
    driver has a representative lap with usable telemetry."""
    reps = select_representative_laps(session)
    if len(reps) == 0:
        return {}, []

    laps_by_driver: dict[str, tuple] = {}
    for driver in reps["Driver"].unique():
        drv_laps = reps[reps["Driver"] == driver]
        lap = drv_laps.loc[drv_laps["LapTime"].idxmin()]
        try:
            tel = lap.get_telemetry().add_distance()
        except Exception:
            continue
        if "Distance" not in tel or len(tel) == 0:
            continue
        laps_by_driver[driver] = (lap, tel)
    if not laps_by_driver:
        return {}, []

    pole_driver = min(laps_by_driver, key=lambda d: laps_by_driver[d][0]["LapTime"])
    _, pole_tel = laps_by_driver[pole_driver]
    grid = build_distance_grid(float(pole_tel["Distance"].max()))
    pole_time_on_grid = resample_to_grid(
        pole_tel["Distance"].tolist(),
        lap_relative_time_s(pole_tel["Time"].dt.total_seconds().tolist()),
        grid,
    )

    out: dict[str, dict] = {}
    for driver, (lap, tel) in laps_by_driver.items():
        distance = tel["Distance"].tolist()
        time_on_grid = resample_to_grid(
            distance, lap_relative_time_s(tel["Time"].dt.total_seconds().tolist()), grid
        )
        out[driver] = {
            "constructor": lap.get("Team"),
            "lap_time_s": lap["LapTime"].total_seconds(),
            "is_pole": driver == pole_driver,
            "speed_kmh": resample_to_grid(distance, tel["Speed"].tolist(), grid),
            "throttle_pct": resample_to_grid(distance, tel["Throttle"].tolist(), grid),
            "delta_s": delta_to_pole_s(time_on_grid, pole_time_on_grid),
        }
    return out, grid


def store_quali_traces(data: WeekendData, db: DBSession) -> None:
    for code, session in data.sessions.items():
        if code != "Q":  # main Qualifying only -- Sprint Qualifying excluded
            continue
        row = db.exec(
            select(Session).where(Session.weekend_id == data.weekend.id, Session.session_type == code)
        ).first()
        if row is None:
            continue
        db.exec(delete(QualiTrace).where(QualiTrace.session_id == row.id))
        traces, grid = extract_quali_traces(session)
        if not traces:
            continue
        corners = [{"number": c.number, "distance_m": c.distance} for c in get_corners(session)]
        for driver, d in traces.items():
            db.add(
                QualiTrace(
                    session_id=row.id,
                    driver=driver,
                    constructor=d["constructor"],
                    lap_time_s=d["lap_time_s"],
                    is_pole=d["is_pole"],
                    grid_m=grid,
                    corners_json=corners,
                    speed_kmh=d["speed_kmh"],
                    throttle_pct=d["throttle_pct"],
                    delta_s=d["delta_s"],
                )
            )
    db.commit()
