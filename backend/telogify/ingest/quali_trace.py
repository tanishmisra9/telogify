"""Distance-aligned qualifying telemetry traces for "The fight to pole": per driver, from the
fastest representative Q lap, speed/throttle/delta-to-pole resampled onto one shared distance
grid so every driver's trace lines up point-for-point.

Reuses the same representative-lap selection as quali_character/deployment (fastest
representative lap per driver, no pooled multi-lap TrackStatus gate). Runs for both main
Qualifying ("Q") and Sprint Qualifying ("SQ") -- each stored under its own session_id, so "the
fight to pole" and "the fight to sprint pole" coexist with no collision. Stored per driver,
idempotently, for every driver with a usable lap -- not just the eventual top two -- so a
future compare-any-two (or add-a-driver) UI needs no re-ingest.

Pole is the OFFICIAL qualifying P1 (session.results Position == 1), not "fastest surviving
lap". A driver whose recorded distance is implausibly far from the field (is_distance_plausible)
is excluded entirely, same as an unparseable lap. If that driver is the pole sitter, NO row is
marked is_pole -- the chart must not promote the runner-up to pole (2026 R3 Japan: pole's lap
recorded 5389m against a ~5770m field). The delta trace still needs a reference lap, so it falls
back to the fastest available lap and the API flags that axis for the frontend to relabel.
Ordering into P1/P2/... is the API's job (it joins SessionResult), not stored here.
"""

import pandas as pd
from sqlmodel import Session as DBSession
from sqlmodel import delete, select

from telogify.analysis.quali_trace import (
    build_distance_grid,
    delta_to_pole_s,
    fraction_aligned_query,
    is_distance_plausible,
    lap_relative_time_s,
    representative_max_distance_m,
    resample_to_grid,
    resolve_pole_reference,
)
from telogify.ingest.loader import WeekendData
from telogify.ingest.quali_character import select_representative_laps
from telogify.ingest.segment import get_corners
from telogify.models import QualiTrace, Session


def _official_positions(session) -> dict[str, int]:
    """{driver code: classified qualifying position} from session.results, empty if unavailable."""
    results = getattr(session, "results", None)
    if results is None or len(results) == 0:
        return {}
    out: dict[str, int] = {}
    for _, r in results.iterrows():
        code, pos = r.get("Abbreviation"), r.get("Position")
        if code is None or pd.isna(pos):
            continue
        out[str(code)] = int(pos)
    return out


def extract_quali_traces(session) -> tuple[dict[str, dict], list[float]]:
    """driver -> {constructor, lap_time_s, is_pole, speed_kmh, throttle_pct, delta_s}, plus the
    shared distance grid (built from the field's median recorded lap distance). Empty ({}, [])
    when no driver has a representative lap with usable, distance-plausible telemetry. is_pole is
    the OFFICIAL qualifying P1 and stays all-False when that driver's lap was scrubbed."""
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

    typical_distance = representative_max_distance_m([float(tel["Distance"].max()) for _, tel in laps_by_driver.values()])
    laps_by_driver = {
        d: (lap, tel)
        for d, (lap, tel) in laps_by_driver.items()
        if is_distance_plausible(float(tel["Distance"].max()), typical_distance)
    }
    if not laps_by_driver:
        return {}, []

    positions = _official_positions(session)
    official_pole = next((d for d, p in positions.items() if p == 1), None)
    lap_times_s = {d: laps_by_driver[d][0]["LapTime"].total_seconds() for d in laps_by_driver}
    pole_driver, reference_driver = resolve_pole_reference(list(laps_by_driver), lap_times_s, official_pole)
    nominal_max = representative_max_distance_m([float(tel["Distance"].max()) for _, tel in laps_by_driver.values()])
    grid = build_distance_grid(nominal_max)

    def time_on_grid_for(tel) -> list[float]:
        distance = tel["Distance"].tolist()
        query = fraction_aligned_query(grid, distance[-1], nominal_max)
        return resample_to_grid(distance, lap_relative_time_s(tel["Time"].dt.total_seconds().tolist()), query)

    pole_time_on_grid = time_on_grid_for(laps_by_driver[reference_driver][1])

    out: dict[str, dict] = {}
    for driver, (lap, tel) in laps_by_driver.items():
        distance = tel["Distance"].tolist()
        query = fraction_aligned_query(grid, distance[-1], nominal_max)
        out[driver] = {
            "constructor": lap.get("Team"),
            "lap_time_s": lap["LapTime"].total_seconds(),
            "is_pole": driver == pole_driver,
            "speed_kmh": resample_to_grid(distance, tel["Speed"].tolist(), query),
            "throttle_pct": resample_to_grid(distance, tel["Throttle"].tolist(), query),
            "delta_s": delta_to_pole_s(time_on_grid_for(tel), pole_time_on_grid),
        }
    return out, grid


def store_quali_traces(data: WeekendData, db: DBSession) -> None:
    for code, session in data.sessions.items():
        if code not in ("Q", "SQ"):
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
        corners = [{"number": c.number, "distance_m": c.distance, "letter": c.letter} for c in get_corners(session)]
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
