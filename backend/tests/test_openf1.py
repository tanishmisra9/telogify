"""Offline tests for the OpenF1 fallback builders. Payloads mirror the real Mexico City 2026 race
shapes (mixed timestamp formats, null sectors, null positions for retirees, etc.)."""

from datetime import datetime

import httpx
import pandas as pd
import pytest

from telogify.ingest import openf1

T0 = pd.Timestamp("2026-11-01T20:00:00")


def _msg(date, message="", category="Other", flag=None, scope=None, sector=None, lap=None):
    return {"date": date, "message": message, "category": category, "flag": flag,
            "scope": scope, "sector": sector, "lap_number": lap, "driver_number": None}


def test_to_naive_utc_parses_mixed_fractional_and_whole_seconds():
    got = openf1.to_naive_utc(["2026-11-01T19:16:37+00:00", "2026-11-01T19:16:37.123000+00:00"])
    assert list(got) == [pd.Timestamp("2026-11-01T19:16:37"), pd.Timestamp("2026-11-01T19:16:37.123")]


def test_match_session_picks_nearest_start_within_window():
    sessions = [
        {"session_key": 1, "date_start": "2026-11-01T18:00:00+00:00"},
        {"session_key": 2, "date_start": "2026-11-01T20:05:00+00:00"},
        {"session_key": 3, "date_start": "2026-11-01T22:00:00+00:00", "is_cancelled": True},
    ]
    assert openf1.match_session(sessions, datetime(2026, 11, 1, 20, 0))["session_key"] == 2
    assert openf1.match_session(sessions, datetime(2026, 11, 2, 9, 0)) is None


def test_derive_deleted_reads_both_message_shapes():
    msgs = [
        {"message": "CAR 10 (GAS) LAP DELETED - TRACK LIMITS AT TURN 12 LAP 2 11:35:28"},
        {"message": "CAR 1 (NOR) TIME 1:20.455 DELETED - TRACK LIMITS AT TURN 12 LAP 52 15:56:06"},
        {"message": "FIA STEWARDS: 5 SECOND TIME PENALTY FOR CAR 16 (LEC)"},
    ]
    assert openf1.derive_deleted(msgs) == {("GAS", 2), ("NOR", 52)}


def _status(msgs, *laps):
    starts = [pd.Timestamp(a) for a, _ in laps]
    ends = [pd.Timestamp(b) for _, b in laps]
    return openf1.derive_track_status(msgs, starts, ends)


def test_track_status_green_throughout_is_exactly_1():
    assert _status([], ("2026-11-01T20:10:00", "2026-11-01T20:11:20")) == ["1"]


def test_track_status_yellow_then_clear_and_sector_scoped_clear():
    msgs = [
        _msg("2026-11-01T20:04:18+00:00", category="Flag", flag="YELLOW", scope="Sector", sector=7),
        _msg("2026-11-01T20:04:23+00:00", category="Flag", flag="CLEAR", scope="Sector", sector=7),
    ]
    # lap spans the yellow: starts green, goes yellow, ends clear
    assert _status(msgs, ("2026-11-01T20:04:00", "2026-11-01T20:05:00")) == ["121"]
    # lap entirely after the clear is clean
    assert _status(msgs, ("2026-11-01T20:05:10", "2026-11-01T20:06:30")) == ["1"]


def test_track_status_safety_car_lap_variants():
    msgs = [
        _msg("2026-11-01T21:00:30+00:00", "SAFETY CAR DEPLOYED", category="SafetyCar"),
        _msg("2026-11-01T21:05:00+00:00", "SAFETY CAR IN THIS LAP", category="SafetyCar"),
    ]
    got = _status(
        msgs,
        ("2026-11-01T21:00:00", "2026-11-01T21:01:20"),  # green then SC deployed mid-lap
        ("2026-11-01T21:02:00", "2026-11-01T21:03:20"),  # SC throughout
    )
    assert got == ["14", "4"]


def test_track_status_vsc_wording_and_ending_phase_until_track_clear():
    # Real Singapore 2026 wording: "VSC DEPLOYED" / "VSC ENDING", then a Track CLEAR flag.
    msgs = [
        _msg("2026-11-01T21:00:30+00:00", "VSC DEPLOYED", category="SafetyCar"),
        _msg("2026-11-01T21:02:00+00:00", "VSC ENDING", category="SafetyCar"),
        _msg("2026-11-01T21:02:15+00:00", "TRACK CLEAR", category="Flag", flag="CLEAR", scope="Track"),
    ]
    assert _status(msgs, ("2026-11-01T21:00:00", "2026-11-01T21:01:20")) == ["16"]
    assert _status(msgs, ("2026-11-01T21:02:05", "2026-11-01T21:02:10")) == ["6"]  # ENDING phase
    assert _status(msgs, ("2026-11-01T21:02:30", "2026-11-01T21:03:50")) == ["1"]


def test_track_status_red_flag_until_session_restart():
    msgs = [
        _msg("2026-11-01T21:10:00+00:00", "RED FLAG - RACE SUSPENDED"),
        _msg("2026-11-01T21:50:00+00:00", "SESSION STARTED", category="SessionStatus"),
    ]
    assert _status(msgs, ("2026-11-01T21:20:00", "2026-11-01T21:21:20")) == ["5"]
    assert _status(msgs, ("2026-11-01T21:55:00", "2026-11-01T21:56:20")) == ["1"]


DRIVERS = [
    {"driver_number": 3, "name_acronym": "VER", "team_name": "Red Bull Racing"},
    {"driver_number": 14, "name_acronym": "ALO", "team_name": "Aston Martin"},
]


def _lap(n, driver, start, dur, s=(30.0, 30.0, 20.0), out=False):
    return {"driver_number": driver, "lap_number": n, "date_start": start, "lap_duration": dur,
            "duration_sector_1": s[0], "duration_sector_2": s[1], "duration_sector_3": s[2],
            "is_pit_out_lap": out}


LAPS = [
    _lap(1, 3, "2026-11-01T20:03:25.510000+00:00", 86.0, out=True),
    _lap(2, 3, "2026-11-01T20:04:51.510000+00:00", 80.0),
    _lap(3, 3, "2026-11-01T20:06:11.510000+00:00", 80.0, s=(30.0, None, 20.0)),  # S2 missing
    _lap(5, 3, "2026-11-01T20:08:51.510000+00:00", 80.0),  # lap 4 absent, as in the real data
    _lap(1, 14, "2026-11-01T20:03:25.510000+00:00", 90.0, out=True),
    _lap(2, 14, "2026-11-01T20:04:55.510000+00:00", None, s=(None, None, None)),  # retired
]
STINTS = [
    {"driver_number": 3, "stint_number": 1, "lap_start": 1, "lap_end": 2, "compound": "MEDIUM", "tyre_age_at_start": 0},
    {"driver_number": 3, "stint_number": 2, "lap_start": 3, "lap_end": 5, "compound": "SOFT", "tyre_age_at_start": 2},
    {"driver_number": 14, "stint_number": 1, "lap_start": 1, "lap_end": 2, "compound": "UNKNOWN", "tyre_age_at_start": 0},
]


def _laps_df(messages=(), pits=(), positions=(), retired=(14,)):
    return openf1.build_laps(LAPS, DRIVERS, STINTS, list(positions), list(messages), list(pits), set(retired), T0)


def _row(df, drv, lap):
    return df[(df.Driver == drv) & (df.LapNumber == lap)].iloc[0]


def test_build_laps_shape_and_missing_lap_is_absent():
    df = _laps_df()
    assert len(df) == 6
    assert sorted(df[df.Driver == "VER"].LapNumber) == [1.0, 2.0, 3.0, 5.0]
    assert df.Time.notna().all()  # a lap with no end time breaks FastF1's weather lookup


def test_build_laps_recovers_a_single_missing_sector_exactly():
    row = _row(_laps_df(), "VER", 3)
    assert row.Sector2Time == pd.Timedelta(seconds=30)
    # two missing sectors cannot be recovered
    assert pd.isna(_row(_laps_df(), "ALO", 2).Sector1Time)


def test_build_laps_stint_compound_and_tyre_life():
    row = _row(_laps_df(), "VER", 5)
    assert (row.Stint, row.Compound, row.TyreLife) == (2.0, "SOFT", 5.0)  # age 2 at start, 3rd lap


def test_build_laps_in_laps_from_stints_pits_and_retirement():
    pits = [{"driver_number": 3, "lap_number": 5}]
    df = _laps_df(pits=pits)
    assert pd.notna(_row(df, "VER", 2).PitInTime)  # stint boundary
    assert pd.notna(_row(df, "VER", 5).PitInTime)  # pit feed
    assert pd.isna(_row(df, "VER", 3).PitInTime)
    assert pd.notna(_row(df, "ALO", 2).PitInTime)  # last lap, short of the session's last lap
    assert pd.notna(_row(df, "VER", 1).PitOutTime)


def test_build_laps_last_lap_is_an_in_lap_only_for_retirees():
    # A lapped finisher's final lap is a normal lap; only a dnf driver's ends in the garage.
    assert pd.isna(_row(_laps_df(retired=()), "ALO", 2).PitInTime)
    assert pd.notna(_row(_laps_df(retired=(14,)), "ALO", 2).PitInTime)


def test_build_laps_opening_lap_is_never_accurate():
    laps = [_lap(1, 3, "2026-11-01T20:03:25.510000+00:00", 86.0, out=False)]  # not even a pit-out
    df = openf1.build_laps(laps, DRIVERS, [], [], [], [], set(), T0)
    assert not df.iloc[0].IsAccurate


def test_build_laps_is_accurate_follows_fastf1_rules():
    df = _laps_df()
    assert not _row(df, "VER", 1).IsAccurate  # out lap / opening lap
    assert not _row(df, "VER", 2).IsAccurate  # in lap
    assert _row(df, "VER", 3).IsAccurate  # recovered sector, sectors sum to the lap
    assert not _row(df, "ALO", 2).IsAccurate  # no lap time


def test_build_laps_deleted_and_track_status_from_race_control():
    msgs = [_msg("2026-11-01T20:06:00+00:00", "CAR 3 (VER) TIME 1:20.000 DELETED - TRACK LIMITS AT TURN 1 LAP 3 14:00:00")]
    df = _laps_df(messages=msgs)
    assert _row(df, "VER", 3).Deleted
    assert not _row(df, "VER", 2).Deleted
    assert (df.TrackStatus == "1").all()


def test_build_laps_position_is_last_change_before_lap_end():
    positions = [
        {"driver_number": 3, "date": "2026-11-01T19:09:06.023000+00:00", "position": 2},
        {"driver_number": 3, "date": "2026-11-01T20:05:00+00:00", "position": 1},
    ]
    df = _laps_df(positions=positions)
    assert _row(df, "VER", 1).Position == 2.0
    assert _row(df, "VER", 3).Position == 1.0


def test_build_laps_marks_each_drivers_best_valid_lap_personal_best():
    df = _laps_df()
    ver = df[df.Driver == "VER"]
    assert list(ver[ver.IsPersonalBest].LapNumber) == [2.0, 3.0, 5.0]  # ties on 80.0 all kept


RACE_ROWS = [
    {"position": 1, "driver_number": 3, "number_of_laps": 71, "dnf": False, "dns": False, "dsq": False, "duration": 8428.772, "gap_to_leader": 0},
    {"position": 2, "driver_number": 44, "number_of_laps": 71, "dnf": False, "dns": False, "dsq": False, "duration": 8429.571, "gap_to_leader": 0.799},
    {"position": 3, "driver_number": 12, "number_of_laps": 70, "dnf": False, "dns": False, "dsq": False, "duration": None, "gap_to_leader": "+1 LAP"},
    {"position": None, "driver_number": 18, "number_of_laps": 5, "dnf": True, "dns": False, "dsq": False, "duration": None, "gap_to_leader": None},
    {"position": None, "driver_number": 41, "number_of_laps": 58, "dnf": True, "dns": False, "dsq": False, "duration": None, "gap_to_leader": None},
    {"position": None, "driver_number": 14, "number_of_laps": 0, "dnf": False, "dns": True, "dsq": False, "duration": None, "gap_to_leader": None},
]
RACE_DRIVERS = [
    {"driver_number": n, "name_acronym": a, "team_name": t}
    for n, a, t in [(3, "VER", "Red Bull Racing"), (44, "HAM", "Ferrari"), (12, "ANT", "Mercedes"),
                    (18, "STR", "Aston Martin"), (41, "LIN", "Racing Bulls"), (14, "ALO", "Aston Martin")]
]


def test_build_results_race_classification_times_and_statuses():
    df = openf1.build_results(RACE_ROWS, RACE_DRIVERS, "Race").set_index("Abbreviation")
    assert list(df.index) == ["VER", "HAM", "ANT", "LIN", "STR", "ALO"]  # retirees by laps, DNS last
    assert list(df.Position) == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    assert df.loc["VER", "Time"] == pd.Timedelta(seconds=8428.772)  # winner: total time
    assert df.loc["HAM", "Time"] == pd.Timedelta(seconds=0.799)  # others: gap
    assert pd.isna(df.loc["ANT", "Time"])  # "+1 LAP" is not a time
    assert list(df.Status) == ["Finished", "Finished", "Lapped", "Retired", "Retired", "Did not start"]


def test_build_results_satisfies_the_race_results_gate_and_gap_extractor():
    from telogify.ingest.results import race_results_complete

    assert race_results_complete(openf1.build_results(RACE_ROWS, RACE_DRIVERS, "Race"))


def test_build_results_is_incomplete_when_openf1_has_no_winner_time_yet():
    from telogify.ingest.results import race_results_complete

    rows = [dict(r, duration=None) for r in RACE_ROWS]
    assert not race_results_complete(openf1.build_results(rows, RACE_DRIVERS, "Race"))


def test_build_results_qualifying_segments():
    rows = [{"position": 1, "driver_number": 44, "number_of_laps": 20, "dnf": False, "dns": False, "dsq": False,
             "duration": [77.341, 76.953, 76.514], "gap_to_leader": [0.0, 0.0, 0.0]}]
    df = openf1.build_results(rows, RACE_DRIVERS, "Qualifying")
    assert df.iloc[0].Q3 == pd.Timedelta(seconds=76.514)
    assert df.iloc[0].Status == ""


def test_build_results_string_position_codes_are_unclassified_not_a_crash():
    # Real Singapore 2026 qualifying: a car that set no time has position "RT", not a number.
    rows = [
        {"position": 1, "driver_number": 3, "number_of_laps": 15, "dnf": False, "dns": False, "dsq": False,
         "duration": [93.2, 91.6, 91.3], "gap_to_leader": [0.8, 0.1, 0.0]},
        {"position": "RT", "driver_number": 44, "number_of_laps": 3, "dnf": False, "dns": False, "dsq": False,
         "duration": [None, None, None], "gap_to_leader": [None, None, None]},
        {"position": 2, "driver_number": 12, "number_of_laps": 20, "dnf": False, "dns": False, "dsq": False,
         "duration": [93.0, 91.9, 91.4], "gap_to_leader": [0.3, 0.4, 0.05]},
    ]
    df = openf1.build_results(rows, RACE_DRIVERS, "Qualifying")
    assert list(df.Abbreviation) == ["VER", "ANT", "HAM"] and df.iloc[2].Status == "Retired"


def test_build_weather_empty_defaults_to_dry():
    # An empty table would make every lap's Rainfall NaN, and bool(NaN) is True: no clean laps.
    df = openf1.build_weather([], T0)
    assert len(df) == 1 and not df.iloc[0].Rainfall


def test_build_weather_converts_rainfall_and_session_time():
    row = {"date": "2026-11-01T20:01:00+00:00", "air_temperature": 22.5, "humidity": 44.4, "pressure": 784.9,
           "rainfall": 1, "track_temperature": 44.3, "wind_direction": 248, "wind_speed": 3.6}
    df = openf1.build_weather([row], T0)
    assert df.iloc[0].Rainfall and df.iloc[0].Time == pd.Timedelta(minutes=1)


def test_build_race_control_uses_fastf1_column_names():
    df = openf1.build_race_control([_msg("2026-11-01T20:04:18+00:00", "X", lap=3)])
    assert {"Time", "Message", "Lap", "Category"} <= set(df.columns) and df.iloc[0].Lap == 3


def test_build_telemetry_channels():
    car = [{"date": "2026-11-01T20:00:00.100000+00:00", "rpm": 11000, "speed": 300, "n_gear": 8, "throttle": 100, "brake": 100, "drs": None}]
    loc = [{"date": "2026-11-01T20:00:00.100000+00:00", "x": 1, "y": 2, "z": 3}]
    c, p = openf1.build_telemetry(car, loc)
    assert c.iloc[0].Brake and c.iloc[0].DRS == 0 and c.iloc[0].Speed == 300.0
    assert (p.iloc[0].X, p.iloc[0].Y) == (1.0, 2.0)


# --- network layer (httpx stubbed) -------------------------------------------------------------


class _Resp:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)


@pytest.fixture
def creds(monkeypatch):
    monkeypatch.setattr("telogify.config.settings.openf1_username", "u")
    monkeypatch.setattr("telogify.config.settings.openf1_password", "p")
    monkeypatch.setattr(openf1, "_token", None)
    monkeypatch.setattr(openf1.time, "sleep", lambda s: None)


def test_get_without_credentials_raises():
    with pytest.raises(openf1.OpenF1Unavailable):
        openf1._get("sessions")


def test_get_treats_404_as_no_rows(creds, monkeypatch):
    monkeypatch.setattr(openf1.httpx, "post", lambda *a, **k: _Resp(200, {"access_token": "t", "expires_in": "3600"}))
    monkeypatch.setattr(openf1.httpx, "get", lambda *a, **k: _Resp(404))
    assert openf1._get("starting_grid", "session_key=1") == []


def test_get_relogs_in_once_on_401(creds, monkeypatch):
    tokens = iter(["old", "new"])
    monkeypatch.setattr(
        openf1.httpx, "post", lambda *a, **k: _Resp(200, {"access_token": next(tokens), "expires_in": "3600"})
    )
    seen = []

    def fake_get(url, headers, timeout):
        seen.append(headers["Authorization"])
        return _Resp(401) if headers["Authorization"] == "Bearer old" else _Resp(200, [{"ok": 1}])

    monkeypatch.setattr(openf1.httpx, "get", fake_get)
    assert openf1._get("sessions") == [{"ok": 1}]
    assert seen == ["Bearer old", "Bearer new"]


def test_get_retries_server_errors_then_succeeds(creds, monkeypatch):
    monkeypatch.setattr(openf1.httpx, "post", lambda *a, **k: _Resp(200, {"access_token": "t", "expires_in": "3600"}))
    answers = iter([_Resp(429), _Resp(503), _Resp(200, [{"ok": 1}])])
    monkeypatch.setattr(openf1.httpx, "get", lambda *a, **k: next(answers))
    assert openf1._get("laps") == [{"ok": 1}]


def test_load_session_raises_when_no_openf1_session_matches(creds, monkeypatch):
    monkeypatch.setattr(openf1, "_get", lambda endpoint, query="": [])
    with pytest.raises(openf1.OpenF1Unavailable):
        openf1.load_session(2026, 19, "Race", datetime(2026, 11, 1, 20, 0))


# --- load_session assembly (OpenF1 + FastF1 Session both stubbed) --------------------------------


def _fake_openf1(monkeypatch, with_telemetry=True):
    """Serve a tiny two-driver session from `_get` and a bare FastF1 Session from get_session."""
    import fastf1.core

    meta = {"session_key": 7, "date_start": "2026-11-01T20:00:00+00:00", "circuit_key": 65,
            "circuit_short_name": "Mexico City"}
    laps = [_lap(1, 3, "2026-11-01T20:03:25.510000+00:00", 86.0, out=True),
            _lap(2, 3, "2026-11-01T20:04:51.510000+00:00", 80.0),
            _lap(1, 14, "2026-11-01T20:03:25.510000+00:00", 90.0, out=True)]
    stints = [s for s in STINTS if s["lap_end"] <= 2]
    car = [{"date": f"2026-11-01T20:04:5{i}.100000+00:00", "rpm": 11000, "speed": 200 + i, "n_gear": 7,
            "throttle": 100, "brake": 0, "drs": 0} for i in range(3)]
    loc = [{"date": f"2026-11-01T20:04:5{i}.100000+00:00", "x": i, "y": i, "z": 0} for i in range(3)]
    weather = [{"date": "2026-11-01T20:00:00+00:00", "air_temperature": 22.0, "humidity": 40.0, "pressure": 780.0,
                "rainfall": 0, "track_temperature": 40.0, "wind_direction": 100, "wind_speed": 1.0}]
    session_result = [{"position": 1, "driver_number": 3, "number_of_laps": 2, "dnf": False, "dns": False,
                       "dsq": False, "duration": 166.0, "gap_to_leader": 0}]
    data = {"sessions": [meta], "drivers": DRIVERS, "laps": laps, "race_control": [], "stints": stints,
            "position": [], "pit": [], "weather": weather, "session_result": session_result,
            "car_data": car if with_telemetry else [], "location": loc if with_telemetry else []}
    monkeypatch.setattr(openf1, "_get", lambda endpoint, query="": data[endpoint])
    monkeypatch.setattr(openf1.fastf1, "get_session", lambda y, r, n: fastf1.core.Session.__new__(fastf1.core.Session))
    monkeypatch.setattr(openf1, "_fastf1_results", lambda *a: None)


def test_load_session_populates_a_fastf1_session_the_extractors_can_read(monkeypatch):
    _fake_openf1(monkeypatch)
    ses = openf1.load_session(2026, 19, "Race", datetime(2026, 11, 1, 20, 0))
    assert len(ses.laps) == 3 and set(ses.car_data) == {"3", "14"}
    assert ses.session_info["Meeting"]["Circuit"]["Key"] == 65
    assert not ses.laps.get_weather_data().iloc[0].Rainfall  # the lookup both clean-lap selectors use
    assert list(ses.results.Abbreviation) == ["VER"] and ses.results.iloc[0].Time == pd.Timedelta(seconds=166)
    assert ses.t0_date == T0
    assert ses.total_laps == 2


def test_load_session_telemetry_is_sliceable_per_lap(monkeypatch):
    _fake_openf1(monkeypatch)
    ses = openf1.load_session(2026, 19, "Race", datetime(2026, 11, 1, 20, 0))
    lap2 = ses.laps[(ses.laps.Driver == "VER") & (ses.laps.LapNumber == 2)].iloc[0]
    assert lap2.get_car_data()["Speed"].max() >= 200


def test_load_session_skips_drivers_without_telemetry_and_fails_without_laps(monkeypatch):
    _fake_openf1(monkeypatch, with_telemetry=False)
    ses = openf1.load_session(2026, 19, "Race", datetime(2026, 11, 1, 20, 0))
    assert ses.car_data == {}  # `_has_usable_data` then rejects it, so the loader skips the session
    monkeypatch.setattr(openf1, "_get", lambda endpoint, query="": [{"session_key": 7, "date_start": "2026-11-01T20:00:00+00:00", "circuit_key": 65}] if endpoint == "sessions" else [])
    with pytest.raises(openf1.OpenF1Unavailable):
        openf1.load_session(2026, 19, "Race", datetime(2026, 11, 1, 20, 0))


def test_fastf1_results_returned_only_when_complete(monkeypatch):
    from types import SimpleNamespace

    from tests.test_loader import _complete_results, _degraded_results

    for results, expect in ((_complete_results(), True), (_degraded_results(), False)):
        probe = SimpleNamespace(load=lambda **k: None, results=results)
        monkeypatch.setattr(openf1.fastf1, "get_session", lambda y, r, n, p=probe: p)
        assert (openf1._fastf1_results(2026, 19, "Race") is not None) is expect

    def boom(y, r, n):
        raise RuntimeError("fastf1 down")

    monkeypatch.setattr(openf1.fastf1, "get_session", boom)
    assert openf1._fastf1_results(2026, 19, "Race") is None
