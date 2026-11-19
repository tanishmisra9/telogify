"""Race-start extraction: per driver, seconds from lights out to 100 and to 200 km/h off the
standing start, plus speed after a fixed distance, from lap-1 car telemetry. Main race only (a sprint start is a different
tyre/fuel story and the page has no sprint card). The maths lives in analysis/race_start.py.
"""

import logging
from statistics import median

import pandas as pd
from sqlmodel import Session as DBSession
from sqlmodel import delete, select

from telogify.analysis.race_start import (
    MIN_FIELD,
    RESTART_MAX_T100_S,
    TIMING_EVIDENCE,
    Skip,
    covers_field,
    grid_field,
    launch_moment,
    launch_outcome,
    restart_clusters,
    speed_at_distance,
    stationary_launches,
)
from telogify.ingest.loader import WeekendData
from telogify.models import RaceRestart, RaceStart, RaceStartSkip, Session

logger = logging.getLogger("telogify.ingest")

_RACE_SESSIONS = ("R",)

# Telemetry window around lap 1's start. Wide, because the field's launch can sit anywhere from
# well before to over a second after the lap timestamp (see analysis/race_start.py), and the car
# must be seen sitting still before it.
_LEAD_S = 8.0
_TAIL_S = 20.0


Skipped = dict[str, tuple[str | None, Skip]]  # driver -> (constructor, why not listed)


def _roster(session) -> dict[str, tuple[str | None, str | None]]:
    """driver code -> (team, status) for everyone in the race classification (incl. non-starters)."""
    try:
        res = session.results
        return {
            r["Abbreviation"]: (
                r["TeamName"] if isinstance(r.get("TeamName"), str) else None,
                r["Status"] if isinstance(r.get("Status"), str) else None,
            )
            for _, r in res.iterrows()
            if isinstance(r.get("Abbreviation"), str) and r["Abbreviation"]
        }
    except Exception:  # results not loaded: the API still falls back to the stored roster
        return {}


def _time_field(cars: dict[str, tuple[str, list[float], list[float]]], skipped: Skipped) -> dict[str, dict] | None:
    """Time one standing start. `cars`: driver -> (team, seconds, km/h) on a common axis. Returns the
    timed rows (`{}` when the start is a finding about the race, with its round-level reason recorded
    in `skipped`), or None when too little car data exists to say anything (a failed read).
    Shared by the original start and every restart so both pass identical rules."""
    moments = {d: m for d, (_, t, v) in cars.items() if (m := launch_moment(t, v)) is not None}
    lights_out, grid = grid_field(moments)
    if lights_out is None:
        if len(cars) < MIN_FIELD:
            return None
        # Enough cars had a speed trace, but too few launched from standstill together to give a
        # shared start (Bahrain 2026: 3 of 22). That is a finding about the race, not a failed read.
        for d, (team, _, _) in cars.items():
            skipped[d] = (team, Skip.NO_COMMON_START)
        return {}

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
        return {}
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
    return rows


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
    lap1_drivers = set(lap1["Driver"])
    # "Did not start" only when the official classification says so. A driver merely missing from
    # the lap table (a truncated or gappy feed) did start, so that is "no speed data", never a
    # fabricated start event.
    skipped: Skipped = {
        d: (team, Skip.DID_NOT_START if status and "did not start" in status.lower() else Skip.NO_DATA)
        for d, (team, status) in roster.items()
        if d not in lap1_drivers
    }
    cars: dict[str, tuple[str, list[float], list[float]]] = {}
    for _, lap in lap1.iterrows():
        driver = lap["Driver"]
        team = lap.get("Team")
        team = team if isinstance(team, str) and team else roster.get(driver, (None, None))[0]
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

    rows = _time_field(cars, skipped)
    if rows is None:
        return {}, {}  # too little car data to say anything about the race: a failed read
    return rows, skipped


def red_flag_times(session) -> list[pd.Timestamp]:
    """When the race was red-flagged, from race control (present on FastF1 AND OpenF1 sessions; OpenF1
    has no session status). A red flag is `Flag == 'RED'` (2024-25) or a message that starts
    `RED FLAG` (2026 has no Flag value). Never a substring test: `CHEQUERED FLAG` contains it."""
    try:
        rc = session.race_control_messages
        msg = rc["Message"].fillna("").astype(str).str.upper().str.strip()
        flag = rc["Flag"].fillna("").astype(str).str.upper() if "Flag" in rc.columns else msg.map(lambda _: "")
        hit = rc[(flag == "RED") | msg.str.startswith("RED FLAG")]
        return sorted(hit["Time"].dropna())
    except Exception:  # race control not loaded
        return []


def extract_restarts(session) -> list[dict[str, dict]]:
    """Every red-flag standing restart of the race, each as driver -> {constructor, t_0_100_s,
    t_0_200_s, v_75m_kmh}, timed by the SAME rules as the original start (`_time_field`). `[]` when
    there is none or it can't be read: never a guess.
    - Only a red flag AFTER the original start counts (Belgium 2025 and Bahrain 2026 were red-flagged
      before the race), so a race whose original start was not measured has no restarts.
    - A restart is a cluster of cars pulling away from a standstill together that the launch maths
      accepts (>= `MIN_FIELD` cars timed, median 0-100 under `RESTART_MAX_T100_S`). Safety-car rolling
      restarts, pit-exit releases and extra formation laps never pass that test.
    - One restart per stoppage: the LAST accepted cluster between a red flag and the next one.
    Lap 1's `LapStartDate` and track status cannot place a restart (lap numbers never reset and the
    first racing lap's timestamp is the line crossing, not lights out), so the cars' own launches do."""
    try:
        laps = session.laps
        car_data = session.car_data
    except Exception:
        return []
    if len(laps) == 0 or "LapStartDate" not in laps.columns:
        return []
    starts = laps[laps["LapNumber"] == 1]["LapStartDate"].dropna()
    if len(starts) == 0:
        return []
    reds = [t for t in red_flag_times(session) if t > starts.min()]
    if not reds:
        return []
    roster = _roster(session)
    drivers: dict[str, tuple[str, object]] = {}  # driver -> (team, driver number)
    for _, lap in laps.drop_duplicates("Driver").iterrows():
        team = lap.get("Team")
        team = team if isinstance(team, str) and team else roster.get(lap["Driver"], (None, None))[0]
        if team:
            drivers[lap["Driver"]] = (team, lap["DriverNumber"])
    series: dict[str, tuple[list[float], list[float]]] = {}
    base = reds[0]
    launches: dict[str, list[float]] = {}
    for d, (_, number) in drivers.items():
        try:
            car = car_data.get(number)
        except Exception:
            continue
        if car is None or len(car) == 0:
            continue
        car = car[car["Date"] > base]
        if len(car) == 0:
            continue
        t = (car["Date"] - base).dt.total_seconds().tolist()
        v = car["Speed"].astype(float).tolist()
        series[d] = (t, v)
        launches[d] = stationary_launches(t, v)
    bounds = [(r - base).total_seconds() for r in reds] + [float("inf")]
    out: list[dict[str, dict]] = []
    for lo, hi in zip(bounds, bounds[1:]):
        accepted: list[dict[str, dict]] = []
        for c in restart_clusters(launches, lo):
            if c >= hi:
                break
            cars = {}
            for d, (t, v) in series.items():
                w = [(ti - c, vi) for ti, vi in zip(t, v) if c - _LEAD_S <= ti <= c + _TAIL_S]
                if w:
                    cars[d] = (drivers[d][0], [a for a, _ in w], [b for _, b in w])
            rows = _time_field(cars, {})
            if rows and median(r["t_0_100_s"] for r in rows.values()) <= RESTART_MAX_T100_S:
                accepted.append(rows)
        if accepted:
            out.append(accepted[-1])
    return out


def extract_race_start(session) -> dict[str, dict]:
    """Just the timed rows (see `extract_race_start_detail`)."""
    return extract_race_start_detail(session)[0]


def should_write(rows: dict[str, dict], skipped: Skipped, has_rows_already: bool) -> bool:
    """Whether a read may replace a session's stored start data.
    - Timed rows always may.
    - A read with NO timed rows never replaces a session that already has timed rows: a degraded
      re-read (a misaligned or partial feed on a `--force` ingest) must not delete a good card.
    - Otherwise it may only when at least MIN_FIELD cars carry a specific timing reason
      (`TIMING_EVIDENCE`): that is a finding about the race. All "no speed data" is a FAILED read."""
    if rows:
        return True
    if has_rows_already:
        return False
    return sum(1 for _, why in skipped.values() if why in TIMING_EVIDENCE) >= MIN_FIELD


def has_timed_rows(db: DBSession, session_id: int) -> bool:
    return db.exec(select(RaceStart.id).where(RaceStart.session_id == session_id)).first() is not None


def write_race_start(db: DBSession, session_id: int, found: dict[str, dict], skipped: Skipped | None = None) -> None:
    """Replace a session's RaceStart AND RaceStartSkip rows (delete + reinsert, idempotent, same
    transaction as the caller's commit)."""
    db.exec(delete(RaceStart).where(RaceStart.session_id == session_id))
    db.exec(delete(RaceStartSkip).where(RaceStartSkip.session_id == session_id))
    for driver, d in found.items():
        db.add(RaceStart(session_id=session_id, driver=driver, **d))
    for driver, (team, why) in (skipped or {}).items():
        db.add(RaceStartSkip(session_id=session_id, driver=driver, constructor=team, reason=why.value))


def has_restart_rows(db: DBSession, session_id: int) -> bool:
    return db.exec(select(RaceRestart.id).where(RaceRestart.session_id == session_id)).first() is not None


def write_race_restarts(db: DBSession, session_id: int, restarts: list[dict[str, dict]]) -> None:
    """Replace a session's RaceRestart rows (delete + reinsert, idempotent). A read that found no
    restart never replaces rows an earlier good read stored (see `store_race_start`)."""
    db.exec(delete(RaceRestart).where(RaceRestart.session_id == session_id))
    for index, rows in enumerate(restarts, start=1):
        for driver, d in rows.items():
            db.add(
                RaceRestart(
                    session_id=session_id,
                    start_index=index,
                    driver=driver,
                    constructor=d["constructor"],
                    t_0_100_s=d["t_0_100_s"],
                    t_0_200_s=d["t_0_200_s"],
                )
            )


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
        if should_write(found, skipped, has_timed_rows(db, row.id)):
            write_race_start(db, row.id, found, skipped)
        if not (found or has_timed_rows(db, row.id)):
            continue  # no measured original start: restarts have nothing to anchor to, and would be orphaned
        try:
            restarts = extract_restarts(session)
        except Exception:  # noqa: BLE001 - optional table, keep the rest of the ingest
            logger.warning("restart extraction failed for session %s; keeping existing rows", code, exc_info=True)
            continue
        if restarts or not has_restart_rows(db, row.id):
            write_race_restarts(db, row.id, restarts)
    db.commit()
