"""Race-start extraction: per driver, seconds from lights out to 100 and to 200 km/h off the
standing start, plus speed after a fixed distance, from lap-1 car telemetry. Main race only (a sprint start is a different
tyre/fuel story and the page has no sprint card). The maths lives in analysis/race_start.py.
"""

import logging

import pandas as pd
from sqlmodel import Session as DBSession
from sqlmodel import delete, select

from telogify.analysis.race_start import (
    MIN_FIELD,
    ROUND_LEVEL,
    Skip,
    covers_field,
    grid_field,
    launch_moment,
    launch_outcome,
    speed_at_distance,
)
from telogify.ingest.loader import WeekendData
from telogify.models import RaceStart, RaceStartSkip, Session

logger = logging.getLogger("telogify.ingest")

_RACE_SESSIONS = ("R",)

# Telemetry window around lap 1's start. Wide, because the field's launch can sit anywhere from
# well before to over a second after the lap timestamp (see analysis/race_start.py), and the car
# must be seen sitting still before it.
_LEAD_S = 8.0
_TAIL_S = 20.0


Skipped = dict[str, tuple[str | None, Skip]]  # driver -> (constructor, why not listed)


def _roster(session) -> dict[str, str | None]:
    """driver code -> team for everyone in the race classification (including non-starters)."""
    try:
        res = session.results
        return {
            r["Abbreviation"]: (r["TeamName"] if isinstance(r.get("TeamName"), str) else None)
            for _, r in res.iterrows()
            if isinstance(r.get("Abbreviation"), str) and r["Abbreviation"]
        }
    except Exception:  # results not loaded: the API still falls back to the stored roster
        return {}


def extract_race_start_detail(session) -> tuple[dict[str, dict], Skipped]:
    """(rows, skipped). `rows`: driver -> {constructor, t_0_100_s, t_0_200_s | None, v_75m_kmh | None},
    timed from the field's shared start instant. `skipped`: every other driver and why (see `Skip`).
    Two passes: every readable car's launch moment gives the shared instant, then each car is timed
    from it. `({}, {})` means a FAILED read (no laps, no car data): nothing is known, nothing should
    be stored. `({}, skipped)` with a round-level reason means the race itself has no comparable start."""
    try:
        laps = session.laps
        car_data = session.car_data
    except Exception:  # FastF1 DataNotLoadedError: telemetry soft-failed (e.g. a --force ingest)
        return {}, {}
    if len(laps) == 0 or "LapStartDate" not in laps.columns:
        return {}, {}
    lap1 = laps[laps["LapNumber"] == 1]
    starts = lap1["LapStartDate"].dropna()
    if len(starts) == 0:
        return {}, {}
    # One shared origin for every car. FastF1 gives all drivers the same lap-1 start; OpenF1's
    # per-driver `date_start` jitters ~100 ms, and keying each car to its own would put the cars
    # on different clocks.
    origin = starts.min()
    roster = _roster(session)
    skipped: Skipped = {
        d: (team, Skip.DID_NOT_START) for d, team in roster.items() if d not in set(lap1["Driver"])
    }
    cars: dict[str, tuple[str, list[float], list[float]]] = {}
    for _, lap in lap1.iterrows():
        driver = lap["Driver"]
        team = lap.get("Team")
        team = team if isinstance(team, str) and team else roster.get(driver)
        # Pit-lane starters are NOT filtered on lap 1's PitOutTime: OpenF1 sets it for every car.
        # They are told apart by launching late (see `grid_field`).
        if pd.isna(lap["LapStartDate"]) or not team:
            skipped[driver] = (team, Skip.NO_DATA)
            continue
        try:
            car = car_data.get(lap["DriverNumber"])
        except Exception:
            car = None
        window = (
            car[(car["Date"] >= origin - pd.Timedelta(seconds=_LEAD_S)) & (car["Date"] <= origin + pd.Timedelta(seconds=_TAIL_S))]
            if car is not None and len(car) > 0
            else None
        )
        if window is None or len(window) == 0:
            skipped[driver] = (team, Skip.NO_DATA)
            continue
        cars[driver] = (
            team,
            (window["Date"] - origin).dt.total_seconds().tolist(),
            window["Speed"].astype(float).tolist(),
        )

    moments = {d: m for d, (_, t, v) in cars.items() if (m := launch_moment(t, v)) is not None}
    lights_out, grid = grid_field(moments)
    if lights_out is None:
        if len(cars) < MIN_FIELD:
            return {}, {}  # too little car data to say anything about the race: a failed read
        # Enough cars had a speed trace, but too few launched from standstill together to give a
        # shared start (Bahrain 2026: 3 of 22). That is a finding about the race, not a failed read.
        for d, (team, _, _) in cars.items():
            skipped[d] = (team, Skip.NO_COMMON_START)
        return {}, skipped

    rows: dict[str, dict] = {}
    for driver, (team, t, v) in cars.items():
        if driver in moments and driver not in grid:
            skipped[driver] = (team, Skip.LATE_LAUNCH)  # launched late: a pit-lane start
            continue
        # A car with no readable launch moment of its own stays eligible: `launch_outcome` still
        # needs it stationary at the shared instant and 100 km/h inside the window, which a
        # pit-lane car that has not left yet cannot satisfy.
        result, why = launch_outcome(t, v, lights_out)
        if result is None:
            skipped[driver] = (team, why)
            continue
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
        for d, r in rows.items():
            skipped[d] = (r["constructor"], Skip.TOO_FEW_TIMED)
        return {}, skipped
    if covers_field(sum(r["t_0_200_s"] is not None for r in rows.values()), n_field):
        # A 200 round: a car that never got there has no comparable time, so it is left out.
        for d, r in rows.items():
            if r["t_0_200_s"] is None:
                skipped[d] = (r["constructor"], Skip.NO_200)
        rows = {d: r for d, r in rows.items() if r["t_0_200_s"] is not None}
    else:
        for r in rows.values():
            r["t_0_200_s"] = None  # not the field: don't show a biased subset
    if not covers_field(sum(r["v_75m_kmh"] is not None for r in rows.values()), n_field):
        for r in rows.values():
            r["v_75m_kmh"] = None
    return rows, skipped


def extract_race_start(session) -> dict[str, dict]:
    """Just the timed rows (see `extract_race_start_detail`)."""
    return extract_race_start_detail(session)[0]


def should_write(rows: dict[str, dict], skipped: Skipped) -> bool:
    """Whether a read may replace a session's stored start data. Timed rows always may. A read with
    no rows may only when it carries a round-level finding (`ROUND_LEVEL`); anything else (no car
    data, a crashed or soft-failed read) is a FAILED read and must never wipe a good round."""
    return bool(rows) or any(why in ROUND_LEVEL for _, why in skipped.values())


def write_race_start(db: DBSession, session_id: int, found: dict[str, dict], skipped: Skipped | None = None) -> None:
    """Replace a session's RaceStart AND RaceStartSkip rows (delete + reinsert, idempotent, same
    transaction as the caller's commit)."""
    db.exec(delete(RaceStart).where(RaceStart.session_id == session_id))
    db.exec(delete(RaceStartSkip).where(RaceStartSkip.session_id == session_id))
    for driver, d in found.items():
        db.add(RaceStart(session_id=session_id, driver=driver, **d))
    for driver, (team, why) in (skipped or {}).items():
        db.add(RaceStartSkip(session_id=session_id, driver=driver, constructor=team, reason=why.value))


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
            found, skipped = extract_race_start_detail(session)
        except Exception:  # noqa: BLE001 - optional table, keep the rest of the ingest
            logger.warning("race start extraction failed for session %s; keeping existing rows", code, exc_info=True)
            continue
        if should_write(found, skipped):
            write_race_start(db, row.id, found, skipped)
    db.commit()
