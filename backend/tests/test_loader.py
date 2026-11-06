import types
from datetime import datetime, timedelta

import fastf1
import pandas as pd
from sqlmodel import select

from telogify.ingest import loader
from telogify.models import RaceWeekend, Session

BASE = datetime(2026, 7, 18, 12, 0, 0)

# Telemetry that actually moves: `_has_usable_data` rejects frames whose top speed is ~0.
_MOVING = {"1": pd.DataFrame({"Speed": [0.0, 310.0]})}


def _complete_results() -> pd.DataFrame:
    """The shape of a complete FastF1 race results table: winner has its total `Time`, every
    row has a `Status`."""
    return pd.DataFrame(
        {
            "Position": [1.0, 2.0, 3.0],
            "Time": [pd.Timedelta(hours=1, minutes=42), pd.Timedelta(seconds=7), pd.Timedelta(seconds=24)],
            "Status": ["Finished", "Finished", "Lapped"],
        }
    )


def _degraded_results() -> pd.DataFrame:
    """FastF1's fallback when the results service is empty/failing: positions present, but no
    Time/Status (the table stored for 2026 rounds 11/13/14/16/17)."""
    return pd.DataFrame(
        {
            "Position": [1.0, 2.0, 3.0],
            "Time": [pd.NaT, pd.NaT, pd.NaT],
            "Status": [None, None, None],
        }
    )


def _healthy_session(results: pd.DataFrame | None = None) -> types.SimpleNamespace:
    """A fake FastF1 session that clears `_has_usable_data`'s probes, for tests exercising
    date-gating/force logic rather than the completeness check itself. `results` defaults to a
    complete table so a Race-named session also clears the results gate."""
    laps = pd.DataFrame({"DriverNumber": [str(i) for i in range(loader._MIN_DRIVERS)]})
    return types.SimpleNamespace(
        load=lambda *a, **k: None,
        laps=laps,
        car_data=_MOVING,
        results=_complete_results() if results is None else results,
    )


def _dated_event(**sessions: str) -> pd.Series:
    """Build an event Series with Session{i}/Session{i}DateUtc pairs, each session an hour
    apart starting a day before BASE, in the given order."""
    fields: dict[str, object] = {}
    for i, (_, name) in enumerate(sessions.items(), start=1):
        fields[f"Session{i}"] = name
        fields[f"Session{i}DateUtc"] = BASE - timedelta(days=1) + timedelta(hours=i)
    return pd.Series(fields)


def test_list_weekend_sessions_sprint_format():
    event = pd.Series(
        {
            "Session1": "Practice 1",
            "Session2": "Sprint Qualifying",
            "Session3": "Sprint",
            "Session4": "Qualifying",
            "Session5": "Race",
        }
    )
    assert loader.list_weekend_sessions(event) == [
        ("FP1", "Practice 1"),
        ("SQ", "Sprint Qualifying"),
        ("SPRINT", "Sprint"),
        ("Q", "Qualifying"),
        ("R", "Race"),
    ]


def test_list_weekend_sessions_skips_empty():
    event = pd.Series(
        {"Session1": "Practice 1", "Session2": "", "Session3": float("nan"), "Session4": "Race"}
    )
    assert loader.list_weekend_sessions(event) == [("FP1", "Practice 1"), ("R", "Race")]


def test_completed_weekend_sessions_respects_buffer():
    # A session isn't eligible at its scheduled start -- only once scheduled end (start +
    # nominal duration) + data lag has passed. FP1 starts at +1h; ready at +1h + 1h (duration)
    # + 1h (lag) = +3h. Race starts at +2h; ready at +2h + 2h (duration) + 1h (lag) = +5h.
    event = _dated_event(s1="Practice 1", s2="Race")
    fp1_start = BASE - timedelta(days=1) + timedelta(hours=1)
    fp1_ready = fp1_start + timedelta(hours=2)
    race_start = BASE - timedelta(days=1) + timedelta(hours=2)
    race_ready = race_start + timedelta(hours=3)

    assert loader.completed_weekend_sessions(event, fp1_ready - timedelta(minutes=1)) == []
    assert loader.completed_weekend_sessions(event, fp1_ready) == [("FP1", "Practice 1")]
    assert loader.completed_weekend_sessions(event, race_ready - timedelta(minutes=1)) == [
        ("FP1", "Practice 1")
    ]
    assert loader.completed_weekend_sessions(event, race_ready) == [
        ("FP1", "Practice 1"),
        ("R", "Race"),
    ]


def test_completed_weekend_sessions_per_type_duration():
    # Each session type's buffer reflects its own nominal duration: SQ/SPRINT (45min) become
    # ready sooner after their start than Q (1h), which becomes ready sooner than R (2h).
    event = _dated_event(s1="Sprint Qualifying", s2="Qualifying", s3="Race")
    sq_start = BASE - timedelta(days=1) + timedelta(hours=1)
    q_start = BASE - timedelta(days=1) + timedelta(hours=2)
    r_start = BASE - timedelta(days=1) + timedelta(hours=3)

    sq_ready = sq_start + timedelta(minutes=45) + timedelta(hours=1)
    q_ready = q_start + timedelta(hours=1) + timedelta(hours=1)
    r_ready = r_start + timedelta(hours=2) + timedelta(hours=1)

    assert loader.completed_weekend_sessions(event, sq_ready) == [("SQ", "Sprint Qualifying")]
    assert loader.completed_weekend_sessions(event, q_ready) == [
        ("SQ", "Sprint Qualifying"),
        ("Q", "Qualifying"),
    ]
    assert loader.completed_weekend_sessions(event, r_ready) == [
        ("SQ", "Sprint Qualifying"),
        ("Q", "Qualifying"),
        ("R", "Race"),
    ]


def test_completed_weekend_sessions_sprint_weekend_by_name_not_slot():
    # Sprint weekend slot ordering varies by year/format; eligibility must be driven by session
    # name, not slot index. Put Sprint Qualifying and Sprint ahead of ordinary practice/quali.
    event = _dated_event(
        s1="Sprint Qualifying", s2="Sprint", s3="Practice 1", s4="Qualifying", s5="Race"
    )
    far_future = BASE + timedelta(days=1)
    assert loader.completed_weekend_sessions(event, far_future) == [
        ("SQ", "Sprint Qualifying"),
        ("SPRINT", "Sprint"),
        ("FP1", "Practice 1"),
        ("Q", "Qualifying"),
        ("R", "Race"),
    ]


def test_completed_weekend_sessions_unmapped_code_uses_default_duration():
    # An unrecognized session name is already filtered out by _NAME_TO_TYPE.get() returning
    # None before duration lookup ever runs -- confirm that path doesn't raise and simply
    # excludes the session, rather than crashing the whole poll on a KeyError.
    event = _dated_event(s1="Practice 1", s2="Some Future Format")
    far_future = BASE + timedelta(days=1)
    assert loader.completed_weekend_sessions(event, far_future) == [("FP1", "Practice 1")]


def test_completed_weekend_sessions_missing_date_excluded():
    event = pd.Series({"Session1": "Practice 1"})  # no date fields at all
    assert loader.completed_weekend_sessions(event, BASE) == []


def test_completed_weekend_sessions_skips_empty():
    event = _dated_event(s1="Practice 1", s2="Race")
    event["Session3"] = ""
    far_future = BASE + timedelta(days=1)
    assert loader.completed_weekend_sessions(event, far_future) == [
        ("FP1", "Practice 1"),
        ("R", "Race"),
    ]


def test_weekend_session_dates_includes_future_sessions():
    # Unlike completed_weekend_sessions, nothing is filtered by date -- every calendar session
    # comes back, including ones scheduled well after `now` would be.
    event = _dated_event(s1="Practice 1", s2="Qualifying", s3="Race")
    dated = loader.weekend_session_dates(event)
    assert [(code, name) for code, name, _date in dated] == [
        ("FP1", "Practice 1"),
        ("Q", "Qualifying"),
        ("R", "Race"),
    ]
    assert all(date is not None for _code, _name, date in dated)


def test_weekend_session_dates_none_when_date_missing():
    event = pd.Series({"Session1": "Practice 1"})
    assert loader.weekend_session_dates(event) == [("FP1", "Practice 1", None)]


def test_session_schedule_returns_empty_on_fastf1_failure(monkeypatch):
    monkeypatch.setattr("telogify.ingest.fastf1_cache.enable_cache", lambda: None)

    def _boom(y, r):
        raise RuntimeError("no network")

    monkeypatch.setattr(fastf1, "get_event", _boom)
    assert loader.session_schedule(2025, 11) == []


def test_session_schedule_delegates_to_weekend_session_dates(monkeypatch):
    event = _dated_event(s1="Practice 1", s2="Race")
    monkeypatch.setattr("telogify.ingest.fastf1_cache.enable_cache", lambda: None)
    monkeypatch.setattr(fastf1, "get_event", lambda y, r: event)

    assert loader.session_schedule(2025, 11) == loader.weekend_session_dates(event)


def test_load_weekend_persists(db_session, monkeypatch):
    event = _dated_event(
        s1="Practice 1", s2="Practice 2", s3="Practice 3", s4="Qualifying", s5="Race"
    )
    event["EventName"] = "Austrian Grand Prix"
    event["Country"] = "Austria"
    event["Location"] = "Spielberg"
    monkeypatch.setattr("telogify.ingest.fastf1_cache.enable_cache", lambda: None)
    monkeypatch.setattr(fastf1, "get_event", lambda y, r: event)
    monkeypatch.setattr(
        fastf1, "get_session", lambda y, r, name: _healthy_session()
    )

    data = loader.load_weekend(2025, 11, db_session, now=BASE)

    weekends = db_session.exec(select(RaceWeekend)).all()
    assert len(weekends) == 1
    assert weekends[0].circuit_name == "Spielberg"
    assert weekends[0].event_name == "Austrian Grand Prix"

    types_present = {s.session_type for s in db_session.exec(select(Session)).all()}
    assert types_present == {"FP1", "FP2", "FP3", "Q", "R"}
    assert set(data.sessions) == types_present


def test_load_weekend_only_ingests_completed_sessions(db_session, monkeypatch):
    event = _dated_event(
        s1="Practice 1", s2="Practice 2", s3="Practice 3", s4="Qualifying", s5="Race"
    )
    event["EventName"] = "Austrian Grand Prix"
    event["Country"] = "Austria"
    event["Location"] = "Spielberg"
    monkeypatch.setattr("telogify.ingest.fastf1_cache.enable_cache", lambda: None)
    monkeypatch.setattr(fastf1, "get_event", lambda y, r: event)
    monkeypatch.setattr(
        fastf1, "get_session", lambda y, r, name: _healthy_session()
    )

    # FP1 (start +1h) and FP2 (start +2h) are ready by +4h (start + 1h duration + 1h lag each,
    # so FP2 is the later-readying of the two); FP3 (start +3h) isn't ready until +5h.
    now = BASE - timedelta(days=1) + timedelta(hours=4)
    data = loader.load_weekend(2025, 11, db_session, now=now)

    types_present = {s.session_type for s in db_session.exec(select(Session)).all()}
    assert types_present == {"FP1", "FP2"}
    assert set(data.sessions) == {"FP1", "FP2"}


def test_load_weekend_skips_already_ingested_sessions(db_session, monkeypatch):
    event = _dated_event(
        s1="Practice 1", s2="Practice 2", s3="Practice 3", s4="Qualifying", s5="Race"
    )
    event["EventName"] = "Austrian Grand Prix"
    event["Country"] = "Austria"
    event["Location"] = "Spielberg"
    monkeypatch.setattr("telogify.ingest.fastf1_cache.enable_cache", lambda: None)
    monkeypatch.setattr(fastf1, "get_event", lambda y, r: event)
    fetched: list[str] = []
    monkeypatch.setattr(
        fastf1,
        "get_session",
        lambda y, r, name: fetched.append(name) or _healthy_session(),
    )

    # First call: only Practice 1/2 are ready (see test_load_weekend_only_ingests_completed_sessions).
    early = BASE - timedelta(days=1) + timedelta(hours=4)
    loader.load_weekend(2025, 11, db_session, now=early)
    assert fetched == ["Practice 1", "Practice 2"]

    # Second call, later: everything has started, but FP1/FP2 are already ingested -- only the
    # newly-completed sessions should be (re)fetched.
    fetched.clear()
    data = loader.load_weekend(2025, 11, db_session, now=BASE)
    # Race is fetched twice: the cheap results probe, then the full load.
    assert fetched == ["Practice 3", "Qualifying", "Race", "Race"]
    assert set(data.sessions) == {"FP3", "Q", "R"}
    types_present = {s.session_type for s in db_session.exec(select(Session)).all()}
    assert types_present == {"FP1", "FP2", "FP3", "Q", "R"}


def test_load_weekend_force_reingests_everything(db_session, monkeypatch):
    event = _dated_event(s1="Practice 1", s2="Practice 2")
    event["EventName"] = "Austrian Grand Prix"
    event["Country"] = "Austria"
    event["Location"] = "Spielberg"
    monkeypatch.setattr("telogify.ingest.fastf1_cache.enable_cache", lambda: None)
    monkeypatch.setattr(fastf1, "get_event", lambda y, r: event)
    fetched: list[str] = []
    monkeypatch.setattr(
        fastf1,
        "get_session",
        lambda y, r, name: fetched.append(name) or _healthy_session(),
    )

    loader.load_weekend(2025, 11, db_session, now=BASE)
    assert fetched == ["Practice 1", "Practice 2"]

    fetched.clear()
    data = loader.load_weekend(2025, 11, db_session, now=BASE, force=True)
    assert fetched == ["Practice 1", "Practice 2"]
    assert set(data.sessions) == {"FP1", "FP2"}


_RAISE = object()  # sentinel: comparing a DataFrame to a string is ambiguous, so use identity


class _FakeSession:
    """Session stand-in whose `.laps`/`.car_data` can be made to raise (mimicking FastF1's
    `DataNotLoadedError` after a soft-failed `.load()`) or return a specific value, to exercise
    `_has_usable_data`'s two probes independently of `load_weekend`."""

    def __init__(self, laps=_RAISE, car_data=_RAISE):
        self._laps = laps
        self._car_data = car_data

    def load(self, *a, **k):
        pass

    @property
    def laps(self):
        if self._laps is _RAISE:
            raise RuntimeError("DataNotLoadedError stand-in")
        return self._laps

    @property
    def car_data(self):
        if self._car_data is _RAISE:
            raise RuntimeError("DataNotLoadedError stand-in")
        return self._car_data


_EMPTY_LAPS = pd.DataFrame({"DriverNumber": []})
_FEW_DRIVER_LAPS = pd.DataFrame({"DriverNumber": ["1", "1", "2"]})
_HEALTHY_LAPS = pd.DataFrame({"DriverNumber": [str(i) for i in range(loader._MIN_DRIVERS)]})


def test_has_usable_data_laps_raises():
    assert loader._has_usable_data(_FakeSession(laps=_RAISE)) is False


def test_has_usable_data_laps_empty():
    ses = _FakeSession(laps=_EMPTY_LAPS, car_data=_MOVING)
    assert loader._has_usable_data(ses) is False


def test_has_usable_data_below_driver_floor():
    ses = _FakeSession(laps=_FEW_DRIVER_LAPS, car_data=_MOVING)
    assert loader._has_usable_data(ses) is False


def test_has_usable_data_car_data_raises():
    ses = _FakeSession(laps=_HEALTHY_LAPS, car_data=_RAISE)
    assert loader._has_usable_data(ses) is False


def test_has_usable_data_car_data_empty():
    ses = _FakeSession(laps=_HEALTHY_LAPS, car_data={})
    assert loader._has_usable_data(ses) is False


def test_has_usable_data_healthy():
    ses = _FakeSession(laps=_HEALTHY_LAPS, car_data=_MOVING)
    assert loader._has_usable_data(ses) is True


def test_load_weekend_leaves_soft_failed_session_unmarked_and_retries(db_session, monkeypatch):
    event = _dated_event(s1="Practice 1")
    event["EventName"] = "Austrian Grand Prix"
    event["Country"] = "Austria"
    event["Location"] = "Spielberg"
    monkeypatch.setattr("telogify.ingest.fastf1_cache.enable_cache", lambda: None)
    monkeypatch.setattr(fastf1, "get_event", lambda y, r: event)
    far_future = BASE + timedelta(days=1)

    # First call: the session "loads" without raising, but has no usable data -- the same
    # shape as a soft-failed FastF1 .load() that returned normally with nothing loaded.
    monkeypatch.setattr(fastf1, "get_session", lambda y, r, name: _FakeSession(laps=_RAISE))
    data = loader.load_weekend(2025, 11, db_session, now=far_future)
    assert data.sessions == {}
    assert db_session.exec(select(Session)).all() == []

    # Second call: the same session now has real data. Because status was never written
    # "loaded" the first time, it's retried rather than permanently skipped via `already`.
    monkeypatch.setattr(fastf1, "get_session", lambda y, r, name: _healthy_session())
    data = loader.load_weekend(2025, 11, db_session, now=far_future)
    assert set(data.sessions) == {"FP1"}
    types_present = {s.session_type for s in db_session.exec(select(Session)).all()}
    assert types_present == {"FP1"}


def test_load_weekend_force_bypasses_completeness_gate(db_session, monkeypatch):
    # force=True is the manual escape hatch: a session that never clears _has_usable_data
    # (e.g. telemetry that's genuinely never published) must still be reachable by hand.
    event = _dated_event(s1="Practice 1")
    event["EventName"] = "Austrian Grand Prix"
    event["Country"] = "Austria"
    event["Location"] = "Spielberg"
    monkeypatch.setattr("telogify.ingest.fastf1_cache.enable_cache", lambda: None)
    monkeypatch.setattr(fastf1, "get_event", lambda y, r: event)
    monkeypatch.setattr(fastf1, "get_session", lambda y, r, name: _FakeSession(laps=_RAISE))

    far_future = BASE + timedelta(days=1)
    data = loader.load_weekend(2025, 11, db_session, now=far_future, force=True)
    assert set(data.sessions) == {"FP1"}
    types_present = {s.session_type for s in db_session.exec(select(Session)).all()}
    assert types_present == {"FP1"}


class _StagedSession:
    """A fake FastF1 session whose `results` differs between the results-only probe
    (`load(laps=False, ...)`) and the full load, and which records every load call, so the
    results gate's two stages can be told apart."""

    def __init__(self, name, probe_results, full_results, log, probe_raises=False):
        self.name = name
        self._probe, self._full, self._log = probe_results, full_results, log
        self._probe_raises = probe_raises
        self._stage = "full"
        self.laps = pd.DataFrame({"DriverNumber": [str(i) for i in range(loader._MIN_DRIVERS)]})
        self.car_data = _MOVING

    def load(self, **kwargs):
        self._stage = "probe" if kwargs.get("laps") is False else "full"
        self._log.append((self.name, self._stage))
        if self._stage == "probe" and self._probe_raises:
            raise RuntimeError("results service down")

    @property
    def results(self):
        return self._probe if self._stage == "probe" else self._full


def _race_weekend_event() -> pd.Series:
    event = _dated_event(s1="Practice 1", s2="Race")
    event["EventName"] = "Singapore Grand Prix"
    event["Country"] = "Singapore"
    event["Location"] = "Marina Bay"
    return event


def _wire(monkeypatch, event, make_session):
    monkeypatch.setattr("telogify.ingest.fastf1_cache.enable_cache", lambda: None)
    monkeypatch.setattr(fastf1, "get_event", lambda y, r: event)
    monkeypatch.setattr(fastf1, "get_session", make_session)


def test_load_weekend_holds_race_until_results_complete(db_session, monkeypatch):
    """The prod bug: a race whose FastF1 results are the degraded position-only table must NOT
    be marked loaded (it would then be skipped forever); it's retried once results complete."""
    log: list = []
    results = {"now": _degraded_results()}
    _wire(
        monkeypatch,
        _race_weekend_event(),
        lambda y, r, name: _StagedSession(name, results["now"], results["now"], log),
    )
    far_future = BASE + timedelta(days=1)

    data = loader.load_weekend(2025, 11, db_session, now=far_future)
    assert set(data.sessions) == {"FP1"}
    assert data.held_back == ["R"]  # surfaced so a manual run can say why nothing was ingested
    assert {s.session_type for s in db_session.exec(select(Session)).all()} == {"FP1"}
    # Race got only the cheap results probe, never the full laps+telemetry load; practice is
    # never probed.
    assert ("Race", "probe") in log and ("Race", "full") not in log
    assert ("Practice 1", "probe") not in log and ("Practice 1", "full") in log

    results["now"] = _complete_results()
    data = loader.load_weekend(2025, 11, db_session, now=far_future)
    assert set(data.sessions) == {"R"} and data.held_back == []
    assert {s.session_type for s in db_session.exec(select(Session)).all()} == {"FP1", "R"}


def test_load_weekend_holds_race_when_full_load_results_are_degraded(db_session, monkeypatch):
    # The probe passing is only an early-out: the table that gets STORED is the full load's.
    log: list = []
    _wire(
        monkeypatch,
        _race_weekend_event(),
        lambda y, r, name: _StagedSession(name, _complete_results(), _degraded_results(), log),
    )
    data = loader.load_weekend(2025, 11, db_session, now=BASE + timedelta(days=1))
    assert "R" not in data.sessions
    assert ("Race", "probe") in log and ("Race", "full") in log


def test_load_weekend_holds_race_when_results_probe_raises(db_session, monkeypatch):
    log: list = []
    _wire(
        monkeypatch,
        _race_weekend_event(),
        lambda y, r, name: _StagedSession(
            name, _complete_results(), _complete_results(), log, probe_raises=(name == "Race")
        ),
    )
    data = loader.load_weekend(2025, 11, db_session, now=BASE + timedelta(days=1))
    assert set(data.sessions) == {"FP1"}


def test_has_complete_results_logs_why_it_says_no_when_results_are_unreadable(caplog):
    # A parsing/shape failure must not masquerade as plain "incomplete results" in the logs.
    class _Broken:
        @property
        def results(self):
            raise ValueError("unexpected column layout")

    with caplog.at_level("WARNING", logger="telogify.ingest"):
        assert loader._has_complete_results(_Broken()) is False
    assert "unexpected column layout" in caplog.text


def test_load_weekend_force_bypasses_results_gate(db_session, monkeypatch):
    # Manual escape hatch for a race whose results genuinely never complete.
    log: list = []
    _wire(
        monkeypatch,
        _race_weekend_event(),
        lambda y, r, name: _StagedSession(name, _degraded_results(), _degraded_results(), log),
    )
    data = loader.load_weekend(2025, 11, db_session, now=BASE + timedelta(days=1), force=True)
    assert set(data.sessions) == {"FP1", "R"}
    assert ("Race", "probe") not in log


# --- telemetry / lap-completeness guards and the OpenF1 fallback --------------------------------


def _race_session(name="Race", longest_lap=71, classified_laps=71, speed=310.0, results=None):
    """A fake race session: `longest_lap` is where the lap table stops, `classified_laps` is the
    leader's lap count in results (a feed cut off mid-race has longest_lap < classified_laps)."""
    res = _complete_results() if results is None else results
    if results is None:
        res["Laps"] = [float(classified_laps)] * len(res)
    return types.SimpleNamespace(
        name=name,
        load=lambda *a, **k: None,
        laps=pd.DataFrame(
            {
                "DriverNumber": [str(i) for i in range(loader._MIN_DRIVERS)],
                "LapNumber": [float(longest_lap)] * loader._MIN_DRIVERS,
            }
        ),
        car_data={"1": pd.DataFrame({"Speed": [0.0, speed]})},
        results=res,
    )


def test_has_usable_data_rejects_telemetry_that_never_moves():
    # FastF1 3.9.1 on Mexico: laps + results fine, every car stationary at 0 km/h.
    assert not loader._has_usable_data(_race_session(speed=0.0))


def test_has_usable_data_rejects_telemetry_without_a_speed_channel():
    ses = _race_session()
    ses.car_data = {"1": object()}
    assert not loader._has_usable_data(ses)


def test_has_usable_data_rejects_race_laps_cut_short_of_the_classified_race():
    # FastF1 3.9.2 on Mexico: laps stop at 56, the classified race was 71.
    assert not loader._has_usable_data(_race_session(longest_lap=56, classified_laps=71))


def test_has_usable_data_tolerates_a_missing_final_lap_record():
    assert loader._has_usable_data(_race_session(longest_lap=69, classified_laps=71))


def test_has_usable_data_lap_check_applies_to_race_like_sessions_only():
    # A practice session has no classified lap count; short laps there are normal.
    ses = _race_session(name="Practice 1", longest_lap=5, classified_laps=71)
    assert loader._has_usable_data(ses)


def test_has_usable_data_lap_check_skipped_when_results_unreadable():
    # No readable leader lap count means "cannot tell"; the results gate owns that case.
    ses = _race_session(results=_degraded_results())
    assert loader._has_usable_data(ses)


_FB_NOW = BASE + timedelta(days=1)  # well past the grace period for every session in the event


def _fallback_setup(monkeypatch, make_fastf1, openf1_session=None, openf1_raises=False, enabled=True):
    """Wire FastF1 (via `make_fastf1`) and a stubbed OpenF1; returns the list of OpenF1 calls."""
    calls: list = []

    def fake_load(year, round, name, start):
        calls.append(name)
        if openf1_raises:
            raise RuntimeError("openf1 down")
        return openf1_session if openf1_session is not None else _race_session(name=name)

    _wire(monkeypatch, _race_weekend_event(), make_fastf1)
    monkeypatch.setattr(loader.openf1, "enabled", lambda: enabled)
    monkeypatch.setattr(loader.openf1, "load_session", fake_load)
    return calls


def _fastf1_race_truncated(y, r, name):
    return _race_session(name=name, longest_lap=56, classified_laps=71) if name == "Race" else _healthy_session()


def test_fallback_used_when_fastf1_race_is_truncated(db_session, monkeypatch):
    calls = _fallback_setup(monkeypatch, _fastf1_race_truncated)
    data = loader.load_weekend(2025, 11, db_session, now=_FB_NOW)
    assert calls == ["Race"]  # practice loaded fine from FastF1, only the broken race fell back
    assert set(data.sessions) == {"FP1", "R"}
    assert data.held_back == []


def test_fallback_not_used_within_grace_period(db_session, monkeypatch):
    # Race is "ready" 3h after its start but FastF1 may still be lagging: not yet a failure.
    calls = _fallback_setup(monkeypatch, _fastf1_race_truncated)
    race_start = BASE - timedelta(days=1) + timedelta(hours=2)
    data = loader.load_weekend(2025, 11, db_session, now=race_start + timedelta(hours=4))
    assert calls == []
    assert "R" not in data.sessions


def test_fallback_never_called_when_fastf1_is_healthy(db_session, monkeypatch):
    calls = _fallback_setup(monkeypatch, lambda y, r, name: _race_session(name=name))
    data = loader.load_weekend(2025, 11, db_session, now=_FB_NOW)
    assert calls == []
    assert set(data.sessions) == {"FP1", "R"}


def test_fallback_disabled_without_credentials(db_session, monkeypatch):
    calls = _fallback_setup(monkeypatch, _fastf1_race_truncated, enabled=False)
    data = loader.load_weekend(2025, 11, db_session, now=_FB_NOW)
    assert calls == []
    assert set(data.sessions) == {"FP1"}  # truncated race skipped, retried next tick


def test_fallback_used_when_fastf1_raises(db_session, monkeypatch):
    def boom(y, r, name):
        if name == "Race":
            raise RuntimeError("day-prefixed timestamp")
        return _healthy_session()

    calls = _fallback_setup(monkeypatch, boom)
    data = loader.load_weekend(2025, 11, db_session, now=_FB_NOW)
    assert calls == ["Race"]
    assert set(data.sessions) == {"FP1", "R"}


def test_fastf1_exception_still_propagates_without_a_fallback(db_session, monkeypatch):
    import pytest

    def boom(y, r, name):
        raise RuntimeError("fastf1 broke")

    _fallback_setup(monkeypatch, boom, enabled=False)
    with pytest.raises(RuntimeError, match="fastf1 broke"):
        loader.load_weekend(2025, 11, db_session, now=_FB_NOW)


def test_openf1_failure_leaves_session_for_next_tick(db_session, monkeypatch):
    calls = _fallback_setup(monkeypatch, _fastf1_race_truncated, openf1_raises=True)
    data = loader.load_weekend(2025, 11, db_session, now=_FB_NOW)
    assert calls == ["Race"]
    assert set(data.sessions) == {"FP1"}
    assert {s.session_type for s in db_session.exec(select(Session)).all()} == {"FP1"}


def test_openf1_result_held_to_the_same_usable_gate(db_session, monkeypatch):
    calls = _fallback_setup(
        monkeypatch, _fastf1_race_truncated, openf1_session=_race_session(speed=0.0)
    )
    data = loader.load_weekend(2025, 11, db_session, now=_FB_NOW)
    assert calls == ["Race"]
    assert "R" not in data.sessions


def test_fallback_used_when_fastf1_results_probe_fails(db_session, monkeypatch):
    # With FastF1 down the results probe fails too; that must not hold the race back forever.
    log: list = []

    def make(y, r, name):
        return _StagedSession(name, _degraded_results(), _degraded_results(), log, probe_raises=True)

    calls = _fallback_setup(monkeypatch, make)
    data = loader.load_weekend(2025, 11, db_session, now=_FB_NOW)
    assert calls == ["Race"]
    assert "R" in data.sessions
    assert data.held_back == []


def test_poll_timeout_is_not_swallowed_by_the_fallback(db_session, monkeypatch):
    import pytest

    from telogify.cli import _PollTimeout

    def timeout(y, r, name):
        raise _PollTimeout()

    _fallback_setup(monkeypatch, timeout)
    with pytest.raises(_PollTimeout):
        loader.load_weekend(2025, 11, db_session, now=_FB_NOW)
