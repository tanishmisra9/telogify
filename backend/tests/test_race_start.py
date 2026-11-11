import pytest

from telogify.analysis.race_start import (
    covers_field,
    grid_field,
    launch_moment,
    launch_times,
    speed_at_distance,
)


def _ramp(rate_kmh_s: float, launch: float, step: float = 0.1, start: float = -3.0, end: float = 14.0):
    """Stationary until `launch`, then a constant acceleration; speed capped at 330."""
    n = int(round((end - start) / step))
    t = [round(start + i * step, 3) for i in range(n)]
    v = [min(330.0, max(0.0, (x - launch) * rate_kmh_s)) for x in t]
    return t, v


def test_launch_moment_recovers_the_true_launch_between_samples():
    t, v = _ramp(40.0, launch=0.43)  # 0.43 falls between 0.4 and 0.5
    assert launch_moment(t, v) == pytest.approx(0.43, abs=1e-6)


def test_launch_moment_none_when_already_moving_or_flat():
    t, v = _ramp(40.0, launch=-5.0)  # moving from the first sample
    assert launch_moment(t, v) is None
    assert launch_moment(t, [0.0] * len(t)) is None
    assert launch_moment([0.0, 1.0], [0.0, 5.0]) is None


def test_grid_field_instant_is_the_median_launch_of_the_grid_starters():
    t0, grid = grid_field({"A": 0.3, "B": 0.4, "C": 0.5, "D": 0.6, "E": 0.9})
    assert t0 == pytest.approx(0.5)
    assert set(grid) == {"A", "B", "C", "D", "E"}


def test_grid_field_drops_late_pit_lane_launchers_and_retakes_the_median():
    moments = {"A": 0.3, "B": 0.4, "C": 0.5, "D": 0.6, "E": 0.7, "PIT1": 9.4, "PIT2": 12.2}
    t0, grid = grid_field(moments)
    assert set(grid) == {"A", "B", "C", "D", "E"}  # launching 9+ s late is not a grid start
    assert t0 == pytest.approx(0.5)  # median of the grid starters only, not dragged by the pit cars


def test_grid_field_keeps_the_latest_real_grid_delay():
    # +0.50 s after the median was the largest delay seen on real grid starters (16 races).
    _, grid = grid_field({"A": 0.4, "B": 0.4, "C": 0.4, "D": 0.4, "E": 0.9})
    assert "E" in grid


def test_grid_field_needs_enough_cars():
    assert grid_field({"A": 0.4, "B": 0.5}) == (None, {})
    # ...including after the late ones are dropped.
    assert grid_field({"A": 0.4, "B": 0.5, "C": 0.5, "PIT1": 9.0, "PIT2": 10.0, "PIT3": 11.0}) == (None, {})


def test_exact_crossings_from_a_shared_start():
    t, v = _ramp(40.0, launch=0.5)  # 100 km/h 2.5 s after launch, 200 after 5.0
    a, b = launch_times(t, v, lights_out_s=0.5)
    assert a == pytest.approx(2.5, abs=1e-6)
    assert b == pytest.approx(5.0, abs=1e-6)


def test_a_slow_reaction_is_included_in_the_time():
    t, v = _ramp(40.0, launch=0.8)  # reacts 0.3 s after the shared lights out
    assert launch_times(t, v, lights_out_s=0.5)[0] == pytest.approx(2.8, abs=1e-6)


def test_an_early_reactor_is_not_rejected():
    t, v = _ramp(40.0, launch=0.3)  # launches 0.2 s before the shared instant
    assert launch_times(t, v, lights_out_s=0.5) is not None


def test_moving_well_before_lights_out_is_not_a_standing_start():
    t, v = _ramp(40.0, launch=-1.5)
    assert launch_times(t, v, lights_out_s=0.5) is None


def test_never_reaching_200_still_has_a_0_100_time():
    t, v = _ramp(40.0, launch=0.5, end=4.0)  # 100 km/h at 2.5 s after launch, 200 never reached
    t100, t200 = launch_times(t, v, lights_out_s=0.5)
    assert t100 == pytest.approx(2.5, abs=1e-6)
    assert t200 is None


def test_never_reaching_100_returns_none():
    t, v = _ramp(40.0, launch=0.5, end=2.0)
    assert launch_times(t, v, lights_out_s=0.5) is None


def test_too_slow_even_for_0_100_returns_none():
    t, v = _ramp(10.0, launch=0.5, end=30.0)  # 100 km/h only after 10 s, beyond the window
    assert launch_times(t, v, lights_out_s=0.5) is None


def test_slow_200_beyond_window_is_dropped_but_0_100_kept():
    t, v = _ramp(15.0, launch=0.5, end=30.0)  # 100 km/h at 6.7 s, 200 km/h at 13.3 s
    t100, t200 = launch_times(t, v, lights_out_s=0.5)
    assert t100 == pytest.approx(6.667, abs=1e-3) and t200 is None


def test_stall_beyond_window_returns_none():
    t, v = _ramp(40.0, launch=9.0, end=30.0)
    assert launch_times(t, v, lights_out_s=0.5) is None


def test_window_must_show_the_car_sitting_still():
    t, v = _ramp(40.0, launch=0.5)
    start = next(i for i, x in enumerate(t) if x > 0.3)
    assert launch_times(t[start:], v[start:], lights_out_s=0.5) is None


def test_degenerate_inputs():
    assert launch_times([], [], 0.5) is None
    assert launch_times([0.0, 1.0], [0.0, 0.0], 0.5) is None
    assert launch_times([0.0, 1.0, 2.0], [0.0, 0.0], 0.5) is None


def test_covers_field_needs_most_of_the_readable_cars():
    assert covers_field(20, 21)
    assert covers_field(15, 21)  # 71%
    assert not covers_field(14, 21)  # 67%
    assert not covers_field(11, 21)  # Baku-style: only the fastest launchers reached 200


def test_covers_field_needs_a_minimum_field():
    assert not covers_field(4, 4)


# ---- extractor, with a fake FastF1-shaped session -------------------------------------------

import pandas as pd

from telogify.ingest.race_start import extract_race_start, store_race_start
from telogify.models import RaceStart, RaceWeekend
from telogify.models import Session as SessionRow
from sqlmodel import Session, select

_T0 = pd.Timestamp("2026-01-01 13:00:00")


def _car(launch: float, rate: float = 40.0, end_speed: float = 330.0, lift_at: float | None = None):
    t = [round(-8.0 + 0.1 * i, 3) for i in range(300)]
    v = [min(end_speed, max(0.0, (x - launch) * rate)) for x in t]
    if lift_at is not None:  # hard lift once past `lift_at` km/h
        i = next(i for i, x in enumerate(v) if x > lift_at)
        v = v[:i] + [max(0.0, v[i - 1] - 15.0 * (j + 1)) for j in range(len(v) - i)]
    return pd.DataFrame({"Date": [_T0 + pd.Timedelta(seconds=x) for x in t], "Speed": v})


class _FakeSession:
    def __init__(self, drivers: dict, pit_out=(), team_nan=(), start_jitter=None, raises=False):
        rows = []
        for i, d in enumerate(drivers):
            start = _T0 + pd.Timedelta(seconds=(start_jitter or {}).get(d, 0.0))
            rows.append(
                {
                    "Driver": d, "DriverNumber": str(i + 1), "LapNumber": 1,
                    "Team": float("nan") if d in team_nan else f"Team{i}",
                    "LapStartDate": start,
                    "PitOutTime": pd.Timedelta(seconds=1) if d in pit_out else pd.NaT,
                }
            )
        self._laps = pd.DataFrame(rows)
        self._cars = {str(i + 1): _car(launch) for i, launch in enumerate(drivers.values())}
        self._raises = raises

    @property
    def laps(self):
        return self._laps

    @property
    def car_data(self):
        if self._raises:
            raise RuntimeError("DataNotLoadedError")
        return self._cars


_FIELD = {f"D{i:02d}": 0.4 + 0.02 * i for i in range(10)}


def test_extractor_skips_a_pit_lane_starter_by_its_late_launch():
    field = {**_FIELD, "PIT": 9.0}  # leaves the pits 9 s after the field launched
    out = extract_race_start(_FakeSession(field))
    assert "PIT" not in out and len(out) == 10
    assert all(0 < v["t_0_100_s"] < v["t_0_200_s"] < 8 for v in out.values())


def test_extractor_does_not_trust_pit_out_time_which_openf1_sets_for_every_car():
    # Regression: Mexico 2026 (OpenF1-built) had a PitOutTime on all 22 lap-1 rows, so every car
    # was skipped as a "pit-lane start" and the round got no card.
    out = extract_race_start(_FakeSession(_FIELD, pit_out=tuple(_FIELD)))
    assert len(out) == 10


def test_extractor_skips_a_nan_team_instead_of_writing_it():
    out = extract_race_start(_FakeSession(_FIELD, team_nan=("D01",)))
    assert "D01" not in out and len(out) == 9


def test_extractor_uses_one_shared_origin_when_lap_starts_jitter():
    # OpenF1-style: each car's own lap start is a little different. Same launch + same real
    # time must give the same result as with identical starts, not per-car-shifted ones.
    base = extract_race_start(_FakeSession(_FIELD))
    jit = extract_race_start(_FakeSession(_FIELD, start_jitter={"D00": 0.1, "D05": 0.15}))
    assert jit.keys() == base.keys()
    for d in base:
        assert jit[d]["t_0_200_s"] == pytest.approx(base[d]["t_0_200_s"], abs=1e-6)


def test_extractor_returns_empty_when_telemetry_never_loaded():
    assert extract_race_start(_FakeSession(_FIELD, raises=True)) == {}


def test_round_where_few_cars_reach_200_keeps_0_100_and_drops_200():
    # Baku/Monaco-style: nearly everyone launches and reaches 100 km/h, almost nobody reaches 200.
    sess = _FakeSession({f"D{i:02d}": 0.4 for i in range(10)})
    sess._cars = {k: _car(0.4, rate=22.0, end_speed=190.0) for k in sess._cars}
    out = extract_race_start(sess)
    assert len(out) == 10
    assert all(v["t_0_200_s"] is None and v["t_0_100_s"] > 0 for v in out.values())


def test_round_with_most_cars_at_200_drops_the_few_that_missed_it():
    sess = _FakeSession(_FIELD)
    sess._cars["1"] = _car(0.4, rate=22.0, end_speed=190.0)  # one car stuck below 200
    out = extract_race_start(sess)
    assert "D00" not in out and len(out) == 9
    assert all(v["t_0_200_s"] is not None for v in out.values())


def test_extractor_attaches_a_km_per_hour_figure():
    out = extract_race_start(_FakeSession(_FIELD))
    assert all(120 < v["v_75m_kmh"] < 180 for v in out.values())


def test_round_where_the_field_lifts_before_the_distance_drops_the_km_h_figure():
    sess = _FakeSession(_FIELD)
    sess._cars = {k: _car(0.4, lift_at=120.0) for k in sess._cars}  # everyone lifts at 120 km/h, ~50 m in
    out = extract_race_start(sess)
    assert out and all(v["v_75m_kmh"] is None for v in out.values())


def test_store_replaces_rows_and_is_idempotent(test_engine):
    from telogify.ingest.loader import WeekendData

    with Session(test_engine) as db:
        wk = RaceWeekend(year=2031, round=1, circuit_name="X", country="Y", event_name="Z GP")
        db.add(wk)
        db.commit()
        db.refresh(wk)
        db.add(SessionRow(weekend_id=wk.id, session_type="R", status="loaded"))
        db.commit()
        data = WeekendData(weekend=wk, sessions={"R": _FakeSession(_FIELD)})
        store_race_start(data, db)
        store_race_start(data, db)  # re-run: delete + reinsert, no duplicates
        rows = db.exec(select(RaceStart)).all()
        assert len(rows) == 10
        # A sprint (or any non-race) session is never stored.
        data2 = WeekendData(weekend=wk, sessions={"SPRINT": _FakeSession(_FIELD)})
        store_race_start(data2, db)
        assert len(db.exec(select(RaceStart)).all()) == 10


# ---- speed after a fixed distance ----------------------------------------------------------


def _accel_trace(a_ms2: float, launch: float = 0.5, step: float = 0.24, n: int = 60):
    """Constant acceleration from rest; speeds in km/h."""
    t = [round(-3.0 + i * step, 4) for i in range(n)]
    v = [max(0.0, a_ms2 * (x - launch)) * 3.6 for x in t]
    return t, v


def test_speed_at_distance_matches_constant_acceleration_exactly():
    # v = sqrt(2*a*d): a = 10 m/s^2 over 75 m -> 38.73 m/s = 139.4 km/h
    t, v = _accel_trace(10.0)
    assert speed_at_distance(t, v, 75.0) == pytest.approx(139.4, abs=0.5)


def test_speed_at_distance_is_independent_of_reaction_time():
    early = speed_at_distance(*_accel_trace(10.0, launch=0.3), 75.0)
    late = speed_at_distance(*_accel_trace(10.0, launch=0.9), 75.0)
    assert early == pytest.approx(late, abs=0.7)


def _simulate(launch: float = 0.5, step: float = 0.24, end: float = 8.0, fine: float = 0.0005):
    """Realistic launch: acceleration falls off with speed, a = 11 * (1 - v/110) m/s^2. Returns the
    trace sampled every `step` seconds (km/h) and the true speed at 75 m from a fine integration."""
    t_grid = [round(-3.0 + i * step, 4) for i in range(int((end + 3.0) / step))]
    vel = x = 0.0
    samples, tt, k = [], -3.0, 0
    truth = None
    while k < len(t_grid):
        if tt >= t_grid[k]:
            samples.append(vel * 3.6)
            k += 1
            continue
        if tt >= launch:
            vel += 11.0 * (1 - vel / 110.0) * fine
            x += vel * fine
            if truth is None and x >= 75.0:
                truth = vel * 3.6
        tt += fine
    return t_grid, samples, truth


def test_speed_at_distance_on_a_concave_realistic_curve():
    t, v, truth = _simulate()
    got = speed_at_distance(t, [round(x) for x in v], 75.0)  # whole-km/h samples, as the feed gives
    assert got == pytest.approx(truth, abs=1.5)


def test_speed_at_distance_none_when_the_car_lifts_first():
    t, v = _accel_trace(10.0)
    i = next(i for i, x in enumerate(v) if x > 60)  # ~60 km/h is reached before 75 m
    for j in range(i, len(v)):  # then it lifts hard
        v[j] = max(0.0, v[i] - 12.0 * (j - i + 1))
    assert speed_at_distance(t, v, 75.0) is None


def test_speed_at_distance_none_when_trace_ends_first():
    t, v = _accel_trace(10.0, n=18)  # ends ~1.3 s after launch
    assert speed_at_distance(t, v, 75.0) is None


def test_speed_at_distance_none_when_not_a_standing_start():
    t = [round(-3.0 + 0.24 * i, 4) for i in range(40)]
    assert speed_at_distance(t, [80.0] * 40, 75.0) is None


# ---- optional-table safety and the refresh path ----------------------------------------------


def _weekend_with_race(db, year=2032, with_rows=True):
    from telogify.ingest.loader import WeekendData

    wk = RaceWeekend(year=year, round=1, circuit_name="X", country="Y", event_name="Z GP")
    db.add(wk)
    db.commit()
    db.refresh(wk)
    race = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
    db.add(race)
    db.commit()
    db.refresh(race)
    if with_rows:
        db.add(RaceStart(session_id=race.id, driver="OLD", constructor="Ferrari", t_0_100_s=2.5, t_0_200_s=4.6))
        db.commit()
    return wk, race, WeekendData


def test_an_empty_read_never_wipes_an_earlier_good_ingest(test_engine):
    with Session(test_engine) as db:
        wk, race, WeekendData = _weekend_with_race(db)
        sess = _FakeSession(_FIELD, raises=True)  # telemetry soft-failed -> extraction returns {}
        store_race_start(WeekendData(weekend=wk, sessions={"R": sess}), db)
        assert [r.driver for r in db.exec(select(RaceStart)).all()] == ["OLD"]


def test_an_extractor_crash_costs_only_this_table(test_engine, monkeypatch):
    from telogify.ingest import race_start as rs

    def boom(session):
        raise ValueError("unexpected dtype")

    monkeypatch.setattr(rs, "extract_race_start", boom)
    with Session(test_engine) as db:
        wk, race, WeekendData = _weekend_with_race(db)
        store_race_start(WeekendData(weekend=wk, sessions={"R": object()}), db)  # must not raise
        assert [r.driver for r in db.exec(select(RaceStart)).all()] == ["OLD"]


def test_refresh_extracts_once_and_never_replaces_good_rows_with_an_empty_read(test_engine, monkeypatch):
    from telogify import pipeline

    monkeypatch.setattr(pipeline, "engine", test_engine)
    with Session(test_engine) as db:
        wk, race, _ = _weekend_with_race(db, year=2033)
    calls = {"n": 0}
    real = pipeline.extract_race_start

    def counting(session):
        calls["n"] += 1
        return real(session)

    monkeypatch.setattr(pipeline, "extract_race_start", counting)
    monkeypatch.setattr(pipeline, "load_race_for_backfill", lambda y, r: _FakeSession(_FIELD))
    found = pipeline.run_refresh_race_start(2033, 1)
    assert len(found) == 10 and calls["n"] == 1  # one extraction, not two
    with Session(test_engine) as db:
        assert len(db.exec(select(RaceStart)).all()) == 10  # replaced the old row

    # An empty read (telemetry too thin) returns None and leaves the good rows alone.
    monkeypatch.setattr(pipeline, "load_race_for_backfill", lambda y, r: _FakeSession(_FIELD, raises=True))
    assert pipeline.run_refresh_race_start(2033, 1) is None
    with Session(test_engine) as db:
        assert len(db.exec(select(RaceStart)).all()) == 10

    # dry run writes nothing
    monkeypatch.setattr(pipeline, "load_race_for_backfill", lambda y, r: _FakeSession({"D00": 0.4, **_FIELD}))
    with Session(test_engine) as db:
        before = len(db.exec(select(RaceStart)).all())
    pipeline.run_refresh_race_start(2033, 1, dry_run=True)
    with Session(test_engine) as db:
        assert len(db.exec(select(RaceStart)).all()) == before


def test_extractor_keeps_a_car_with_no_readable_launch_moment_of_its_own():
    # Australia 2026: a car whose first climb is too ragged to fit still launched with the field and
    # is timed from the shared instant. Only a car that LAUNCHED LATE is dropped.
    sess = _FakeSession(_FIELD)
    ragged = sess._cars["1"].copy()
    ragged["Speed"] = [0.0 if x < 0.9 else 90.0 + 30.0 * (x - 0.9) for x in [(d - _T0).total_seconds() for d in ragged["Date"]]]
    sess._cars["1"] = ragged  # no 10-60 km/h climb at all: launch_moment is None
    out = extract_race_start(sess)
    assert "D00" in out
