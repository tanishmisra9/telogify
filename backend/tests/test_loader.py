import types
from datetime import datetime, timedelta

import fastf1
import pandas as pd
from sqlmodel import select

from telogify.ingest import loader
from telogify.models import RaceWeekend, Session

BASE = datetime(2026, 7, 18, 12, 0, 0)


def _healthy_session() -> types.SimpleNamespace:
    """A fake FastF1 session that clears `_has_usable_data`'s probes, for tests exercising
    date-gating/force logic rather than the completeness check itself."""
    laps = pd.DataFrame({"DriverNumber": [str(i) for i in range(loader._MIN_DRIVERS)]})
    return types.SimpleNamespace(load=lambda *a, **k: None, laps=laps, car_data={"1": object()})


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
    # + 1h (lag) = +3h. Race starts at +2h; ready at +2h + 2h30 (duration) + 1h (lag) = +5h30.
    event = _dated_event(s1="Practice 1", s2="Race")
    fp1_start = BASE - timedelta(days=1) + timedelta(hours=1)
    fp1_ready = fp1_start + timedelta(hours=2)
    race_start = BASE - timedelta(days=1) + timedelta(hours=2)
    race_ready = race_start + timedelta(hours=3, minutes=30)

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
    # ready sooner after their start than Q (1h), which becomes ready sooner than R (2h30).
    event = _dated_event(s1="Sprint Qualifying", s2="Qualifying", s3="Race")
    sq_start = BASE - timedelta(days=1) + timedelta(hours=1)
    q_start = BASE - timedelta(days=1) + timedelta(hours=2)
    r_start = BASE - timedelta(days=1) + timedelta(hours=3)

    sq_ready = sq_start + timedelta(minutes=45) + timedelta(hours=1)
    q_ready = q_start + timedelta(hours=1) + timedelta(hours=1)
    r_ready = r_start + timedelta(hours=2, minutes=30) + timedelta(hours=1)

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
    assert fetched == ["Practice 3", "Qualifying", "Race"]
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
    ses = _FakeSession(laps=_EMPTY_LAPS, car_data={"1": object()})
    assert loader._has_usable_data(ses) is False


def test_has_usable_data_below_driver_floor():
    ses = _FakeSession(laps=_FEW_DRIVER_LAPS, car_data={"1": object()})
    assert loader._has_usable_data(ses) is False


def test_has_usable_data_car_data_raises():
    ses = _FakeSession(laps=_HEALTHY_LAPS, car_data=_RAISE)
    assert loader._has_usable_data(ses) is False


def test_has_usable_data_car_data_empty():
    ses = _FakeSession(laps=_HEALTHY_LAPS, car_data={})
    assert loader._has_usable_data(ses) is False


def test_has_usable_data_healthy():
    ses = _FakeSession(laps=_HEALTHY_LAPS, car_data={"1": object()})
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
