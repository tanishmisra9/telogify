"""A fake FastF1 session that the DB extractors (`extract_*` / `store_*`) accept.

`laps` is a real `fastf1.core.Laps` (so `.loc[idxmin]`, `.iterlaps()` and boolean masking behave
as in production) and per-lap telemetry is a real `fastf1.core.Telemetry`, served by patching
`Lap.get_telemetry` (see `patch_telemetry`).

Landmine: `Telemetry.add_distance()` REPLACES any `Distance` column with the integral of
Speed over Time. quali_trace / deployment / accel_samples call it, so lap length in those
fixtures comes from `lap_telemetry`'s speed and `DT_S`, not from a column set by hand.
"""

import types

import numpy as np
import pandas as pd
from fastf1.core import Lap, Laps, Telemetry

DT_S = 0.2


def td(seconds: float) -> pd.Timedelta:
    return pd.Timedelta(seconds=seconds)


def lap_row(
    driver: str,
    lap_number: int,
    lap_time_s: float | None,
    *,
    team: str = "Team",
    stint: int = 1,
    compound: str | None = "MEDIUM",
    tyre_life: float | None = None,
    position: float | None = None,
    pit_in: bool = False,
    pit_out: bool = False,
    accurate: bool = True,
    deleted: bool = False,
    track_status: str = "1",
    sectors: tuple[float | None, float | None, float | None] = (None, None, None),
    start_s: float | None = None,
) -> dict:
    """One FastF1-shaped lap row. Lap N starts where lap N-1 ended unless `start_s` is given."""
    start = start_s if start_s is not None else (lap_number - 1) * 100.0
    end = start + (lap_time_s if lap_time_s is not None else 100.0)
    s1, s2, s3 = sectors
    return {
        "Driver": driver,
        "Team": team,
        "LapNumber": float(lap_number),
        "LapTime": td(lap_time_s) if lap_time_s is not None else pd.NaT,
        "Stint": float(stint),
        "Compound": compound,
        "TyreLife": tyre_life if tyre_life is not None else float(lap_number),
        "Position": float(position) if position is not None else np.nan,
        "PitInTime": td(end) if pit_in else pd.NaT,
        "PitOutTime": td(start) if pit_out else pd.NaT,
        "IsAccurate": accurate,
        "Deleted": deleted,
        "TrackStatus": track_status,
        "Time": td(end),
        "LapStartTime": td(start),
        "Sector1Time": td(s1) if s1 is not None else pd.NaT,
        "Sector2Time": td(s2) if s2 is not None else pd.NaT,
        "Sector3Time": td(s3) if s3 is not None else pd.NaT,
    }


def fake_session(
    rows: list[dict],
    *,
    corners: list[tuple[int, float, str]] | None = None,
    results: pd.DataFrame | None = None,
    circuit_info_raises: bool = False,
) -> types.SimpleNamespace:
    """rows -> a session with `laps`, dry `weather_data`, `get_circuit_info()` and `results`."""
    laps = Laps(pd.DataFrame(rows))
    weather = pd.DataFrame({"Time": [td(0.0)], "Rainfall": [False]})
    if corners:
        info = types.SimpleNamespace(
            corners=pd.DataFrame(
                {
                    "Number": [c[0] for c in corners],
                    "Distance": [c[1] for c in corners],
                    "Letter": [c[2] for c in corners],
                }
            )
        )
    else:
        info = types.SimpleNamespace(corners=pd.DataFrame({"Number": [], "Distance": [], "Letter": []}))

    def get_circuit_info():
        if circuit_info_raises:
            raise ValueError("telemetry won't merge")
        return info

    return types.SimpleNamespace(
        laps=laps, weather_data=weather, get_circuit_info=get_circuit_info, results=results
    )


def lap_telemetry(scale: float = 1.0, *, clip: bool = True) -> Telemetry:
    """A plausible flying lap: ramp to ~320 km/h at full throttle, (optionally) fade at full
    throttle like an ERS clip, then brake hard and crawl through a corner, repeated twice so the
    lap has two straights. X/Y run in a straight line, so lateral g is ~0. `scale` stretches
    speeds, which is how a test makes one driver's integrated lap length differ from another's."""
    speed: list[float] = []
    throttle: list[float] = []
    brake: list[bool] = []
    for _ in range(2):
        for k in range(40):  # ramp 200 -> 317 km/h
            speed.append(200 + 3 * k)
            throttle.append(100.0)
            brake.append(False)
        for k in range(20):  # fade at full throttle (the clip)
            speed.append(320 - (1.5 * k if clip else 0))
            throttle.append(100.0)
            brake.append(False)
        for k in range(12):  # brake into the corner
            speed.append(290 - 15 * k)
            throttle.append(0.0)
            brake.append(True)
        for _k in range(6):  # corner apex
            speed.append(100.0)
            throttle.append(30.0)
            brake.append(False)
    speed_arr = np.array(speed, dtype=float) * scale
    n = len(speed_arr)
    t = pd.to_timedelta(np.arange(n) * DT_S, unit="s")
    x = np.cumsum(speed_arr / 3.6 * DT_S) * 10  # decimetres, as FastF1 reports X/Y
    tel = Telemetry(
        {
            "Time": t,
            "SessionTime": t,
            "Speed": speed_arr,
            "Throttle": np.array(throttle),
            "Brake": np.array(brake),
            "nGear": np.full(n, 8),
            "X": x,
            "Y": np.zeros(n),
        }
    )
    # straights / quali_character read tel["Distance"] without calling add_distance(); the
    # integral is the same one add_distance() computes, so both kinds of caller agree.
    return tel.add_distance()


def patch_telemetry(monkeypatch, by_driver: dict[str, Telemetry | None]) -> None:
    """Make `Lap.get_telemetry` return `by_driver[driver]`; a None entry raises, like the real
    Monaco-tunnel merge failure the extractors guard with `except Exception: continue`."""

    def get_telemetry(self, **_kwargs):
        tel = by_driver[self["Driver"]]
        if tel is None:
            raise ValueError("telemetry won't merge")
        return tel.copy()

    monkeypatch.setattr(Lap, "get_telemetry", get_telemetry)
