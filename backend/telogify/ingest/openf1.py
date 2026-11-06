"""OpenF1 fallback: rebuild a session FastF1 cannot deliver.

`load_session` returns a real `fastf1.core.Session` (from `fastf1.get_session`, never `.load()`ed)
whose private data attributes are filled from OpenF1, so every existing `store_*` extractor runs
unchanged -- they only ever see the FastF1 shape. The builders below are pure (plain lists and
DataFrames in, DataFrames out) so they are unit-tested offline; only `_get` and `load_session`
touch the network.

Things OpenF1 does not provide are derived, and are the places this can differ from FastF1:
TrackStatus (from race-control flags), Deleted (track-limit messages), IsAccurate, per-lap Position,
pit in/out laps. OpenF1 telemetry is ~3.7 Hz vs FastF1's ~4.2 Hz.
"""

import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import fastf1
import httpx
import pandas as pd
from fastf1.core import Laps, SessionResults, Telemetry

from telogify.config import settings

logger = logging.getLogger("telogify.ingest.openf1")

_API = "https://api.openf1.org"
_RETRIES = 4
_TELEMETRY_WORKERS = 3  # ponytail: paid-tier rate limit undocumented; raise if fetches are slow
_SESSION_MATCH = timedelta(minutes=30)
_WINDOW_PAD = timedelta(minutes=15)
# FastF1's IsAccurate tolerance for the sector-sum check.
_SECTOR_TOLERANCE = pd.Timedelta(milliseconds=3)

_QUALI_NAMES = {"Qualifying", "Sprint Qualifying", "Sprint Shootout"}
_RACE_NAMES = {"Race", "Sprint"}


class OpenF1Unavailable(Exception):
    """No credentials, no matching session, or no usable data from OpenF1."""


def enabled() -> bool:
    return bool(settings.openf1_username and settings.openf1_password)


# --------------------------------------------------------------------------------------------
# Network
# --------------------------------------------------------------------------------------------

_token: tuple[str, float] | None = None
_token_lock = threading.Lock()


def _bearer(refresh: bool = False) -> str:
    global _token
    with _token_lock:
        if refresh or _token is None or time.monotonic() > _token[1]:
            resp = httpx.post(
                f"{_API}/token",
                data={"username": settings.openf1_username, "password": settings.openf1_password},
                timeout=30,
            )
            resp.raise_for_status()
            body = resp.json()
            # Refresh a minute early so a long fetch never straddles the 1h expiry.
            _token = (body["access_token"], time.monotonic() + int(body["expires_in"]) - 60)
        return _token[0]


def _get(endpoint: str, query: str = "") -> list[dict]:
    """GET /v1/<endpoint>?<query> -> list of rows. `query` is a raw query string because OpenF1
    filters use operators in the key (`date>=...`). 404 means "no rows". Retries 429/5xx with
    backoff and re-logs-in once on 401."""
    if not enabled():
        raise OpenF1Unavailable("OPENF1_USERNAME/OPENF1_PASSWORD not set")
    url = f"{_API}/v1/{endpoint}" + (f"?{query}" if query else "")
    refreshed = False
    for attempt in range(_RETRIES):
        resp = httpx.get(url, headers={"Authorization": f"Bearer {_bearer()}"}, timeout=120)
        if resp.status_code == 401 and not refreshed:
            _bearer(refresh=True)
            refreshed = True
            continue
        if resp.status_code == 404:
            return []
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < _RETRIES - 1:
            time.sleep(2 ** (attempt + 1))
            continue
        resp.raise_for_status()
        return resp.json()
    raise OpenF1Unavailable(f"OpenF1 {endpoint}: retries exhausted")


# --------------------------------------------------------------------------------------------
# Pure builders
# --------------------------------------------------------------------------------------------


def to_naive_utc(values) -> pd.Series:
    """OpenF1 timestamps mix `...:00+00:00` and `...:00.123000+00:00`; both must parse."""
    return pd.to_datetime(pd.Series(values), utc=True, format="ISO8601").dt.tz_convert(None)


def _fmt(ts: pd.Timestamp | datetime) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m-%dT%H:%M:%S")


def match_session(sessions: list[dict], start_utc: datetime) -> dict | None:
    """The OpenF1 session starting closest to the FastF1-scheduled start (within 30 min).
    Matched by time, not name, so OpenF1's sprint-session naming never matters."""
    best, best_gap = None, _SESSION_MATCH
    for s in sessions:
        if s.get("is_cancelled"):
            continue
        gap = abs(to_naive_utc([s["date_start"]]).iloc[0] - pd.Timestamp(start_utc))
        if gap <= best_gap:
            best, best_gap = s, gap
    return best


_DELETED_RE = re.compile(r"\((\w{3})\)\s+(?:TIME [\d:.]+ |LAP )DELETED.*\bLAP (\d+)\b")


def derive_deleted(messages: list[dict]) -> set[tuple[str, int]]:
    """(driver code, lap) pairs whose time was deleted, e.g. for track limits."""
    out = set()
    for m in messages:
        found = _DELETED_RE.search(str(m.get("message") or "").upper())
        if found:
            out.add((found.group(1), int(found.group(2))))
    return out


def _dominant(yellow: bool, sc: bool, vsc: bool, red: bool) -> str:
    """The single TrackStatus code in force (FastF1's feed carries one at a time):
    5 red > 4 SC > 6 VSC > 2 yellow > 1 clear."""
    return "5" if red else "4" if sc else "6" if vsc else "2" if yellow else "1"


def _track_status_timeline(messages: list[dict]) -> list[tuple[pd.Timestamp, str]]:
    """[(time, TrackStatus code in force from then on)] from race-control flags/SC/VSC/red."""
    yellow: set = set()
    sc = vsc = red = False
    timeline: list[tuple[pd.Timestamp, str]] = []
    rows = sorted(messages, key=lambda m: m["date"])
    stamps = to_naive_utc([m["date"] for m in rows]) if rows else []
    for m, at in zip(rows, stamps):
        msg = str(m.get("message") or "").upper()
        cat = m.get("category")
        flag = (m.get("flag") or "").upper()
        if cat == "Flag":
            key = (m.get("scope"), m.get("sector"))
            if flag in ("YELLOW", "DOUBLE YELLOW"):
                yellow.add(key)
            elif flag == "CLEAR":
                if m.get("scope") == "Track":
                    yellow.clear()
                    vsc = False  # the VSC (including its ENDING phase) lasts until the track is clear
                else:
                    yellow.discard(key)
            elif flag == "GREEN":
                yellow.clear()
        elif "VIRTUAL SAFETY CAR" in msg or msg.startswith("VSC"):
            # OpenF1 words these "VSC DEPLOYED" / "VSC ENDING". ENDING is still non-green in
            # FastF1's feed (status 7), so it keeps the VSC flag on until the track-clear message.
            vsc = "DEPLOYED" in msg or "ENDING" in msg
        elif cat == "SafetyCar" and "SAFETY CAR" in msg:
            sc = "DEPLOYED" in msg
        elif "RED FLAG" in msg:
            red = True
        elif cat == "SessionStatus" and ("STARTED" in msg or "RESUMED" in msg):
            red = False
        timeline.append((at, _dominant(bool(yellow), sc, vsc, red)))
    return timeline


def derive_track_status(
    messages: list[dict], starts: list[pd.Timestamp], ends: list[pd.Timestamp]
) -> list[str]:
    """Per-lap FastF1-style TrackStatus string: the code in force when the lap began followed by
    each change during it, consecutive repeats collapsed ('1' = green throughout, '14' = green
    then safety car, '4' = safety car throughout)."""
    timeline = _track_status_timeline(messages)
    out = []
    for start, end in zip(starts, ends):
        if pd.isna(start):
            out.append("1")
            continue
        end = start if pd.isna(end) else end
        seq = ["1"]
        for at, code in timeline:
            if at <= start:
                seq = [code]  # state in force when the lap began
            elif at <= end:
                if seq[-1] != code:
                    seq.append(code)
            else:
                break
        out.append("".join(seq))
    return out


def reconcile_stints(stints: list[dict], pits: list[dict]) -> list[dict]:
    """OpenF1's stint table is right about the compounds, in order, but its boundaries can be
    wrong: Singapore 2026 lists Alonso's second stint as laps 2-61 although the pit feed (and
    FastF1) show a single stop on lap 35. When a driver has exactly one more stint than pit stops,
    the pit laps are the true boundaries. Otherwise (e.g. tyres changed under a red flag with no
    pit-feed row) the stints are left exactly as OpenF1 reports them."""
    out: list[dict] = []
    for drv in sorted({s["driver_number"] for s in stints}):
        mine = sorted((s for s in stints if s["driver_number"] == drv), key=lambda s: s["stint_number"])
        stops = sorted({p["lap_number"] for p in pits if p["driver_number"] == drv and p.get("lap_number")})
        last = max(s["lap_end"] for s in mine)
        if len(mine) == len(stops) + 1 and all(1 <= lap < last for lap in stops):
            starts, ends = [1] + [lap + 1 for lap in stops], stops + [last]
            out += [dict(s, lap_start=a, lap_end=b) for s, a, b in zip(mine, starts, ends)]
        else:
            out += mine
    return out


def build_laps(
    laps: list[dict],
    drivers: list[dict],
    stints: list[dict],
    positions: list[dict],
    messages: list[dict],
    pits: list[dict],
    retired: set[int],
    t0: pd.Timestamp,
) -> pd.DataFrame:
    """FastF1-shaped laps table from OpenF1 `laps` + `stints` + `position` + `race_control`.
    Laps OpenF1 does not report are simply absent, as in FastF1."""
    who = {d["driver_number"]: d for d in drivers}
    stints = reconcile_stints(stints, pits)
    df = pd.DataFrame([l for l in laps if l["driver_number"] in who and l.get("date_start")])
    if df.empty:
        return pd.DataFrame()
    df = df.sort_values(["driver_number", "lap_number"]).reset_index(drop=True)
    df["start"] = to_naive_utc(df["date_start"])
    # OpenF1 sometimes omits one sector (e.g. S2 on lap 4 for half the Mexico grid) while still
    # reporting the lap time. A lap is the sum of its sectors, so a single missing one is exact.
    sectors = df[[f"duration_sector_{i}" for i in (1, 2, 3)]]
    only_one_missing = (sectors.isna().sum(axis=1) == 1) & df["lap_duration"].notna()
    remainder = df["lap_duration"] - sectors.sum(axis=1)
    for col in sectors.columns:
        fill = only_one_missing & df[col].isna()
        df.loc[fill, col] = remainder[fill].round(3)
    dur = pd.to_timedelta(df["lap_duration"], unit="s")
    nxt = df.groupby("driver_number")["start"].shift(-1)
    # Lap end: the next lap's start when there is one, else start + duration, else the start itself
    # (FastF1 never has a lap without an end time, and weather lookup breaks on one).
    end = nxt.where(nxt.notna(), df["start"] + dur).fillna(df["start"])

    out = pd.DataFrame(
        {
            "Driver": df["driver_number"].map(lambda n: who[n]["name_acronym"]),
            "DriverNumber": df["driver_number"].astype(str),
            "Team": df["driver_number"].map(lambda n: who[n]["team_name"]),
            "LapNumber": df["lap_number"].astype(float),
            "LapTime": dur,
            "LapStartDate": df["start"],
            "LapStartTime": df["start"] - t0,
            "Time": end - t0,
        }
    )
    for i in (1, 2, 3):
        out[f"Sector{i}Time"] = pd.to_timedelta(df[f"duration_sector_{i}"], unit="s")

    # Stint / compound / tyre age from the stints table (lap_start..lap_end inclusive).
    stint_no = pd.Series(float("nan"), index=df.index)
    compound = pd.Series(None, index=df.index, dtype=object)
    tyre_life = pd.Series(float("nan"), index=df.index)
    in_lap = pd.Series(False, index=df.index)
    last_stint = {}
    for s in stints:
        last_stint[s["driver_number"]] = max(last_stint.get(s["driver_number"], 0), s["stint_number"])
    for s in stints:
        m = (df["driver_number"] == s["driver_number"]) & df["lap_number"].between(
            s["lap_start"], s["lap_end"]
        )
        stint_no[m] = s["stint_number"]
        compound[m] = s["compound"]
        tyre_life[m] = s["tyre_age_at_start"] + (df.loc[m, "lap_number"] - s["lap_start"]) + 1
        if s["stint_number"] < last_stint[s["driver_number"]]:
            in_lap |= (df["driver_number"] == s["driver_number"]) & (df["lap_number"] == s["lap_end"])
    # Pit entries (incl. a retirement into the garage) also mark in-laps; stint boundaries miss some.
    pitted = {(p["driver_number"], p["lap_number"]) for p in pits if p.get("lap_number")}
    in_lap |= pd.Series(
        [(n, l) in pitted for n, l in zip(df["driver_number"], df["lap_number"])], index=df.index
    )
    # A retiree's last lap ends in the garage (FastF1 marks it as an in-lap too); it is never a
    # clean flying lap. Only `dnf` drivers: a lapped finisher's last lap is a normal lap.
    last_lap = df.groupby("driver_number")["lap_number"].transform("max")
    in_lap |= df["driver_number"].isin(retired) & (df["lap_number"] == last_lap)
    out["Stint"] = stint_no
    out["Compound"] = compound
    out["TyreLife"] = tyre_life
    out["PitOutTime"] = out["LapStartTime"].where(df["is_pit_out_lap"].fillna(False).astype(bool))
    out["PitInTime"] = out["Time"].where(in_lap)

    # Per-lap Position: the last position change at or before the lap ends.
    out["Position"] = float("nan")
    if positions:
        pos = pd.DataFrame(positions)
        pos["t"] = to_naive_utc(pos["date"])
        pos = pos.sort_values("t")
        key = (end.fillna(df["start"])).rename("t")
        probe = pd.DataFrame({"driver_number": df["driver_number"], "t": key}).sort_values("t")
        merged = pd.merge_asof(
            probe, pos[["t", "driver_number", "position"]], on="t", by="driver_number"
        )
        out.loc[probe.index, "Position"] = merged["position"].to_numpy()

    deleted = derive_deleted(messages)
    out["Deleted"] = [
        (d, int(n)) in deleted for d, n in zip(out["Driver"], out["LapNumber"])
    ]
    out["TrackStatus"] = derive_track_status(messages, list(df["start"]), list(end))

    # IsAccurate mirrors fastf1.core.Session._check_lap_accuracy except its lap-continuity check:
    # not lap 1, no pit in/out, green or yellow only, lap and all three sectors present with sectors summing
    # to the lap time, previous lap not under the safety car. Continuity (lap end == next lap
    # start, 3 ms) cannot be evaluated: OpenF1's `date_start` is a sample time that jitters by
    # ~100 ms, not the line-crossing time FastF1 has, and the lap time itself is the same
    # official timing value.
    sector_sum = out["Sector1Time"] + out["Sector2Time"] + out["Sector3Time"]
    out["IsAccurate"] = (
        out["PitOutTime"].isna()
        & out["PitInTime"].isna()
        & (out["LapNumber"] > 1)  # FastF1 never trusts a standing-start opening lap
        & out["TrackStatus"].isin(["1", "2", "12", "21"])
        & out["LapTime"].notna()
        & sector_sum.notna()
        & ((sector_sum - out["LapTime"]).abs() <= _SECTOR_TOLERANCE)
        & (out.groupby("DriverNumber")["TrackStatus"].shift(1) != "4")
    ).to_numpy()

    # IsPersonalBest: only FastF1's `pick_fastest` (corner-distance reference) reads it. Mark each
    # driver's best non-deleted lap rather than replaying the running-best history.
    valid = out["LapTime"].notna() & ~out["Deleted"]
    best = out["LapTime"].where(valid).groupby(out["DriverNumber"]).transform("min")
    out["IsPersonalBest"] = valid & (out["LapTime"] == best)
    return out.reset_index(drop=True)


def _td(seconds) -> pd.Timedelta:
    return pd.NaT if seconds is None or (isinstance(seconds, float) and pd.isna(seconds)) else pd.to_timedelta(float(seconds), unit="s")


def build_results(rows: list[dict], drivers: list[dict], session_name: str) -> pd.DataFrame:
    """FastF1-shaped SessionResults from OpenF1 `session_result`.

    Race-like: classified finishers first, then retirees by laps completed (the API lists them in
    that order; equal-lap ties keep the API order and cannot be verified), then DNS/DSQ. P1's
    `Time` is the total race time, others' the gap to the leader (FastF1 semantics).
    Qualifying: Q1/Q2/Q3 from the duration arrays."""
    who = {d["driver_number"]: d for d in drivers}
    # `position` is an int for a classified car but a status code ("RT", "DSQ", ...) otherwise.
    rows = [
        dict(r, position=r["position"] if isinstance(r["position"], int) else None,
             code=r["position"] if isinstance(r["position"], str) else None)
        for r in rows if r["driver_number"] in who
    ]
    is_race = session_name in _RACE_NAMES
    is_quali = session_name in _QUALI_NAMES

    def rank(r):
        # classified first (by position), then everyone else by laps desc, DNS/DSQ last
        if r["position"] is not None:
            return (0, r["position"], 0)
        out_ = r.get("dns") or r.get("dsq") or r.get("code") in ("DNS", "DSQ")
        return (1, 1 if out_ else 0, -(r.get("number_of_laps") or 0))

    ordered = sorted(rows, key=rank)  # stable: equal keys keep API order
    leader_laps = next((r["number_of_laps"] for r in ordered if r["position"] == 1), None)
    out = []
    for i, r in enumerate(ordered, start=1):
        d = who[r["driver_number"]]
        laps = r.get("number_of_laps")
        code = r.get("code")
        if r.get("dsq") or code == "DSQ":
            status = "Disqualified"
        elif r.get("dns") or code == "DNS":
            status = "Did not start"
        elif r.get("dnf") or code in ("RT", "DNF"):
            status = "Retired"
        elif is_race and leader_laps and laps is not None and laps < leader_laps:
            status = "Lapped"
        else:
            status = "Finished" if is_race else ""
        row = {
            "DriverNumber": str(r["driver_number"]),
            "Abbreviation": d["name_acronym"],
            "TeamName": d["team_name"],
            "Position": float(i),
            "Laps": float(laps) if laps is not None else float("nan"),
            "Status": status,
            "Time": pd.NaT,
            "Q1": pd.NaT,
            "Q2": pd.NaT,
            "Q3": pd.NaT,
        }
        if is_race:
            if i == 1 and r.get("position") == 1:
                row["Time"] = _td(r.get("duration"))
            elif isinstance(r.get("gap_to_leader"), (int, float)):
                row["Time"] = _td(r["gap_to_leader"])
        if is_quali and isinstance(r.get("duration"), list):
            for k, v in zip(("Q1", "Q2", "Q3"), r["duration"]):
                row[k] = _td(v)
        out.append(row)
    return pd.DataFrame(out)


def build_weather(rows: list[dict], t0: pd.Timestamp) -> pd.DataFrame:
    df = pd.DataFrame(
        {
            "Time": to_naive_utc([r["date"] for r in rows]) - t0,
            "AirTemp": [r["air_temperature"] for r in rows],
            "Humidity": [r["humidity"] for r in rows],
            "Pressure": [r["pressure"] for r in rows],
            "Rainfall": [bool(r["rainfall"]) for r in rows],
            "TrackTemp": [r["track_temperature"] for r in rows],
            "WindDirection": [r["wind_direction"] for r in rows],
            "WindSpeed": [r["wind_speed"] for r in rows],
        }
    )
    if df.empty:
        # An empty weather table makes every lap's Rainfall NaN, and bool(NaN) is True: no lap
        # would ever be clean. Dry, constant conditions are the safe stand-in.
        logger.warning("OpenF1 returned no weather; assuming dry")
        df = pd.DataFrame(
            {"Time": [pd.Timedelta(0)], "AirTemp": [float("nan")], "Humidity": [float("nan")],
             "Pressure": [float("nan")], "Rainfall": [False], "TrackTemp": [float("nan")],
             "WindDirection": [0], "WindSpeed": [float("nan")]}
        )
    return df


def build_race_control(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Time": to_naive_utc([r["date"] for r in rows]),
            "Category": [r["category"] for r in rows],
            "Message": [r["message"] for r in rows],
            "Status": [None] * len(rows),
            "Flag": [r["flag"] for r in rows],
            "Scope": [r["scope"] for r in rows],
            "Sector": [r["sector"] for r in rows],
            "RacingNumber": [r["driver_number"] for r in rows],
            "Lap": [r["lap_number"] for r in rows],
        }
    )


def build_telemetry(car_rows: list[dict], loc_rows: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(car, pos) frames in FastF1's raw channel layout (Date + channels + Source)."""
    car = pd.DataFrame(
        {
            "Date": to_naive_utc([r["date"] for r in car_rows]),
            "RPM": [r["rpm"] for r in car_rows],
            "Speed": [float(r["speed"]) for r in car_rows],
            "nGear": [r["n_gear"] for r in car_rows],
            "Throttle": [float(r["throttle"]) for r in car_rows],
            "Brake": [bool(r["brake"]) for r in car_rows],
            "DRS": [int(r["drs"] or 0) for r in car_rows],
            "Source": "car",
        }
    )
    pos = pd.DataFrame(
        {
            "Date": to_naive_utc([r["date"] for r in loc_rows]),
            "Status": "OnTrack",
            "X": [float(r["x"]) for r in loc_rows],
            "Y": [float(r["y"]) for r in loc_rows],
            "Z": [float(r["z"]) for r in loc_rows],
            "Source": "pos",
        }
    )
    return car, pos


# --------------------------------------------------------------------------------------------
# Session assembly
# --------------------------------------------------------------------------------------------


def _fastf1_results(year: int, round: int, name: str) -> pd.DataFrame | None:
    """FastF1's own results when complete: they carry the official classification, including the
    order of retirees on equal laps that OpenF1 cannot give. None if unavailable/degraded."""
    from telogify.ingest.results import race_results_complete

    try:
        probe = fastf1.get_session(year, round, name)
        probe.load(laps=False, telemetry=False, weather=False, messages=False)
        return probe.results if race_results_complete(probe.results) else None
    except Exception as exc:
        logger.warning("%s %s %s: FastF1 results unavailable (%s)", year, round, name, exc)
        return None


def load_session(year: int, round: int, name: str, start_utc: datetime) -> "fastf1.core.Session":
    """A FastF1 Session populated entirely from OpenF1 (results from FastF1 when complete).
    Raises OpenF1Unavailable / httpx errors; the caller treats any failure as "skip this tick"."""
    meta = match_session(_get("sessions", f"year={year}"), start_utc)
    if meta is None:
        raise OpenF1Unavailable(f"no OpenF1 session near {start_utc} in {year}")
    key = meta["session_key"]
    t0 = to_naive_utc([meta["date_start"]]).iloc[0]

    drivers = _get("drivers", f"session_key={key}")
    laps = _get("laps", f"session_key={key}")
    if not laps or not drivers:
        raise OpenF1Unavailable(f"OpenF1 has no laps/drivers for session {key}")
    lap_starts = to_naive_utc([l["date_start"] for l in laps if l.get("date_start")])
    lap_ends = lap_starts.max() + pd.Timedelta(seconds=max(l.get("lap_duration") or 0 for l in laps) + 1)
    lo, hi = min(t0, lap_starts.min()) - _WINDOW_PAD, lap_ends + _WINDOW_PAD
    win = f"date>={_fmt(lo)}&date<{_fmt(hi)}"

    messages = _get("race_control", f"session_key={key}&{win}")
    stints = _get("stints", f"session_key={key}")
    positions = _get("position", f"session_key={key}")
    pits = _get("pit", f"session_key={key}&{win}")
    weather = _get("weather", f"session_key={key}&{win}")
    results = _get("session_result", f"session_key={key}")

    ses = fastf1.get_session(year, round, name)
    ses._t0_date = t0
    ses._session_info = {"Meeting": {"Circuit": {"Key": meta["circuit_key"], "ShortName": meta.get("circuit_short_name")}}}
    ses._laps = Laps(build_laps(laps, drivers, stints, positions, messages, pits,
                   {r["driver_number"] for r in results if r.get("dnf")}, t0), session=ses)
    ses._weather_data = build_weather(weather, t0)
    ses._race_control_messages = build_race_control(messages)

    res = _fastf1_results(year, round, name) if name in _RACE_NAMES else None
    ses._results = res if res is not None else SessionResults(build_results(results, drivers, name))
    ses._total_laps = int(ses._laps["LapNumber"].max())

    def fetch(d: dict):
        n = d["driver_number"]
        q = f"session_key={key}&driver_number={n}&{win}"
        return str(n), build_telemetry(_get("car_data", q), _get("location", q))

    ses._car_data, ses._pos_data = {}, {}
    with ThreadPoolExecutor(_TELEMETRY_WORKERS) as pool:
        for n, (car, pos) in pool.map(fetch, drivers):
            if car.empty or pos.empty:
                continue
            for src, store in ((car, ses._car_data), (pos, ses._pos_data)):
                tel = Telemetry(src, session=ses, driver=n, drop_unknown_channels=True, _cast_default_cols=True)
                tel["Date"] = tel["Date"].dt.round("ms")
                tel["Time"] = tel["Date"] - t0
                tel["SessionTime"] = tel["Time"]
                store[n] = tel
    logger.info("%s %s %s: built from OpenF1 session %s", year, round, name, key)
    return ses
