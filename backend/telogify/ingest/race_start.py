"""Race-start extraction: per driver, seconds from lights out to 100 and to 200 km/h off the
standing start, plus speed after a fixed distance, from lap-1 car telemetry. Main race only (a sprint start is a different
tyre/fuel story and the page has no sprint card). The maths lives in analysis/race_start.py.
"""

import logging

import pandas as pd
from sqlmodel import Session as DBSession
from sqlmodel import delete, select

from telogify.analysis.race_start import (
    covers_field,
    grid_field,
    launch_moment,
    launch_times,
    speed_at_distance,
)
from telogify.ingest.loader import WeekendData
from telogify.models import RaceStart, Session

logger = logging.getLogger("telogify.ingest")

_RACE_SESSIONS = ("R",)

# Telemetry window around lap 1's start. Wide, because the field's launch can sit anywhere from
# well before to over a second after the lap timestamp (see analysis/race_start.py), and the car
# must be seen sitting still before it.
_LEAD_S = 8.0
_TAIL_S = 20.0


def extract_race_start(session) -> dict[str, dict]:
    """driver -> {constructor, t_0_100_s, t_0_200_s | None, v_75m_kmh | None}. Two passes: every readable car's launch
    moment gives the field's shared lights-out instant, then each car is timed from it. A driver
    whose start can't be read cleanly is simply absent (pit-lane start, moving before lights out).
    `{}` for the whole round when too few cars could be timed (see `covers_field`)."""
    try:
        laps = session.laps
        car_data = session.car_data
    except Exception:  # FastF1 DataNotLoadedError: telemetry soft-failed (e.g. a --force ingest)
        return {}
    if len(laps) == 0 or "LapStartDate" not in laps.columns:
        return {}
    lap1 = laps[laps["LapNumber"] == 1]
    starts = lap1["LapStartDate"].dropna()
    if len(starts) == 0:
        return {}
    # One shared origin for every car. FastF1 gives all drivers the same lap-1 start; OpenF1's
    # per-driver `date_start` jitters ~100 ms, and keying each car to its own would put the cars
    # on different clocks.
    origin = starts.min()
    cars: dict[str, tuple[str, list[float], list[float]]] = {}
    for _, lap in lap1.iterrows():
        team = lap.get("Team")
        # Pit-lane starters are NOT filtered on lap 1's PitOutTime: OpenF1 sets it for every car.
        # They are told apart by launching late (see `grid_field`).
        if pd.isna(lap["LapStartDate"]) or not isinstance(team, str) or not team:
            continue
        try:
            car = car_data.get(lap["DriverNumber"])
        except Exception:
            continue
        if car is None or len(car) == 0:
            continue
        window = car[
            (car["Date"] >= origin - pd.Timedelta(seconds=_LEAD_S))
            & (car["Date"] <= origin + pd.Timedelta(seconds=_TAIL_S))
        ]
        if len(window) == 0:
            continue
        cars[lap["Driver"]] = (
            team,
            (window["Date"] - origin).dt.total_seconds().tolist(),
            window["Speed"].astype(float).tolist(),
        )

    moments = {d: m for d, (_, t, v) in cars.items() if (m := launch_moment(t, v)) is not None}
    lights_out, grid = grid_field(moments)
    if lights_out is None:
        return {}

    rows: dict[str, dict] = {}
    for driver, (team, t, v) in cars.items():
        if driver in moments and driver not in grid:
            continue  # launched late: a pit-lane start, not a grid start
        # A car with no readable launch moment of its own stays eligible: `launch_times` still
        # needs it stationary at the shared instant and 100 km/h inside the window, which a
        # pit-lane car that has not left yet cannot satisfy.
        result = launch_times(t, v, lights_out)
        if result is not None:
            rows[driver] = {
                "constructor": team,
                "t_0_100_s": result[0],
                "t_0_200_s": result[1],
                "v_75m_kmh": speed_at_distance(t, v),
            }

    # Each figure is shown only when most of the cars that sat on the grid and launched have it
    # (`grid` is that field). 0-100 km/h is the floor: no round without it.
    n_field = len(grid)
    if not covers_field(len(rows), n_field):
        return {}
    if covers_field(sum(r["t_0_200_s"] is not None for r in rows.values()), n_field):
        # A 200 round: a car that never got there has no comparable time, so it is left out.
        rows = {d: r for d, r in rows.items() if r["t_0_200_s"] is not None}
    else:
        for r in rows.values():
            r["t_0_200_s"] = None  # not the field: don't show a biased subset
    if not covers_field(sum(r["v_75m_kmh"] is not None for r in rows.values()), n_field):
        for r in rows.values():
            r["v_75m_kmh"] = None
    return rows


def write_race_start(db: DBSession, session_id: int, found: dict[str, dict]) -> None:
    """Replace a session's RaceStart rows with `found` (delete + reinsert, idempotent)."""
    db.exec(delete(RaceStart).where(RaceStart.session_id == session_id))
    for driver, d in found.items():
        db.add(RaceStart(session_id=session_id, driver=driver, **d))


def store_race_start(data: WeekendData, db: DBSession) -> None:
    """Race start is an optional table: a failed or empty read must cost only this table, never the
    whole ingest, and must never wipe rows from an earlier good read (a `--force` re-ingest whose
    telemetry soft-failed would otherwise delete a round's start card)."""
    for code, session in data.sessions.items():
        if code not in _RACE_SESSIONS:
            continue
        row = db.exec(
            select(Session).where(Session.weekend_id == data.weekend.id, Session.session_type == code)
        ).first()
        if row is None:
            continue
        try:
            found = extract_race_start(session)
        except Exception:  # noqa: BLE001 - optional table, keep the rest of the ingest
            logger.warning("race start extraction failed for session %s; keeping existing rows", code, exc_info=True)
            continue
        if found:
            write_race_start(db, row.id, found)
    db.commit()
