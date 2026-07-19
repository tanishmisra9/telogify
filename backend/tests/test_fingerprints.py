import numpy as np
import pandas as pd
from sqlmodel import select

from telogify.analysis.fingerprints import (
    aggregate_fingerprint,
    corner_features,
    dtw_distance,
    extract_fingerprints,
    resample,
    store_fingerprints,
)


def test_dtw_distance_identical_is_zero():
    assert dtw_distance([1, 2, 3], [1, 2, 3]) == 0.0


def test_dtw_distance_single_mismatch():
    assert dtw_distance([0, 0, 0], [0, 1, 0]) == 1.0


def test_dtw_distance_different_length_sequences():
    assert dtw_distance([1, 2], [1, 2, 3, 4]) == 3.0


def test_corner_features_from_v_shaped_trace():
    grid = np.linspace(100, 200, 11)  # lo=100, step 10
    speed = np.array([300, 280, 250, 220, 200, 180, 210, 250, 290, 310, 320])
    throttle = np.array([0, 0, 0, 0, 0, 0, 30, 60, 90, 100, 100])
    brake = np.array([1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0])
    gear = np.array([8, 7, 6, 5, 4, 3, 4, 5, 6, 7, 8])

    f = corner_features(grid, speed, throttle, brake, gear)

    assert f.min_speed == 180.0
    assert f.gear == 3
    assert f.brake_point == 0.0  # braking from window start
    assert f.trail_brake_dur == 50.0  # window start (100) to apex (150)
    assert f.throttle_point == 60.0  # reapplied at grid index 6 (160) -> relative 60
    assert abs(f.throttle_ramp - 1.75) < 1e-9  # (100-30)/(200-160)
    assert f.steer_at_apex is None  # no steering channel


def _trace(speed):
    return {
        "grid": np.linspace(0, 100, 5),
        "speed": np.array(speed, float),
        "throttle": np.array([0, 0, 0, 50, 100], float),
        "brake": np.array([1, 1, 0, 0, 0], float),
        "gear": np.array([5, 4, 3, 4, 5], float),
    }


def test_aggregate_drops_dtw_outlier_lap():
    traces = [
        _trace([100, 80, 60, 80, 100]),
        _trace([102, 82, 62, 82, 102]),
        _trace([98, 78, 58, 78, 98]),
        _trace([10, 10, 10, 10, 10]),  # wild outlier
    ]
    feat, kept = aggregate_fingerprint(traces)

    assert kept == 3  # outlier rejected
    assert abs(feat.min_speed - 60.0) < 1e-9  # mean of 60, 62, 58


def test_resample_interpolates_onto_grid():
    grid, values = resample([0.0, 10.0], [100.0, 200.0], lo=0.0, hi=10.0, n=3)
    assert list(grid) == [0.0, 5.0, 10.0]
    assert list(values) == [100.0, 150.0, 200.0]


# --- extract_fingerprints: FastF1-boundary mocked with duck-typed fakes --------------------


class _FakeLap:
    def __init__(self, driver, compound, tel=None, raises=False):
        self._data = {"Driver": driver, "Compound": compound}
        self._tel = tel
        self._raises = raises

    def __getitem__(self, key):
        return self._data[key]

    def get_telemetry(self):
        if self._raises:
            raise RuntimeError("telemetry merge failed")
        return self._tel


class _FakeClean:
    def __init__(self, laps):
        self._laps = laps

    def __len__(self):
        return len(self._laps)

    def iterlaps(self):
        return enumerate(self._laps)


def _fake_telemetry(lo=400.0, hi=600.0, n=60):
    distance = np.linspace(lo, hi, n)
    mid = n // 2
    speed = np.concatenate([np.linspace(300, 150, mid), np.linspace(150, 300, n - mid)])
    throttle = np.concatenate([np.zeros(mid), np.linspace(0, 100, n - mid)])
    brake = np.concatenate([np.ones(mid), np.zeros(n - mid)])
    gear = np.concatenate([np.linspace(6, 2, mid), np.linspace(2, 6, n - mid)])
    return pd.DataFrame(
        {"Distance": distance, "Speed": speed, "Throttle": throttle, "Brake": brake, "nGear": gear}
    )


def test_extract_fingerprints_windows_groups_and_skips_bad_laps(monkeypatch):
    from telogify.analysis import fingerprints as fp_module
    from telogify.ingest.segment import Corner

    laps = [
        _FakeLap("LEC", "SOFT", _fake_telemetry()),
        _FakeLap("LEC", "SOFT", _fake_telemetry()),
        _FakeLap("LEC", None, _fake_telemetry()),  # falsy compound -> "UNKNOWN"
        _FakeLap("VER", "SOFT", raises=True),  # telemetry merge fails -> skipped
    ]
    clean = _FakeClean(laps)

    monkeypatch.setattr(fp_module, "select_clean_laps", lambda session: clean)
    # corner 1 (distance 500) is covered by the fake telemetry's 400-600 range; corner 2
    # (distance 5000) is nowhere near it -> "if not traces: continue" for every group.
    monkeypatch.setattr(fp_module, "get_corners", lambda session: [Corner(1, 500.0), Corner(2, 5000.0)])

    results = extract_fingerprints(object(), n=20)

    assert {(driver, corner, compound) for driver, corner, compound, _, _ in results} == {
        ("LEC", 1, "SOFT"),
        ("LEC", 1, "UNKNOWN"),
    }
    for _, _, _, feat, count in results:
        assert feat.min_speed is not None
        assert count >= 1


def test_extract_fingerprints_empty_when_no_clean_laps(monkeypatch):
    from telogify.analysis import fingerprints as fp_module

    monkeypatch.setattr(fp_module, "select_clean_laps", lambda session: _FakeClean([]))
    assert extract_fingerprints(object()) == []


# --- store_fingerprints: DB orchestration, extract_fingerprints itself mocked --------------


def test_store_fingerprints_persists_rows_and_skips_unmatched_session(db_session, monkeypatch):
    from telogify.analysis import fingerprints as fp_module
    from telogify.ingest.loader import WeekendData
    from telogify.models import Fingerprint, RaceWeekend, Session as SessionRow

    wk = RaceWeekend(year=2069, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    fp1 = SessionRow(weekend_id=wk.id, session_type="FP1", status="loaded")
    db_session.add(fp1)
    db_session.commit()
    db_session.refresh(fp1)

    def fake_extract(session, n=50):
        return [("LEC", 1, "SOFT", corner_features(
            np.linspace(400, 600, 5), [300, 250, 200, 250, 300], [0, 0, 0, 50, 100], [1, 1, 0, 0, 0], [5, 4, 3, 4, 5]
        ), 3)]

    monkeypatch.setattr(fp_module, "extract_fingerprints", fake_extract)

    data = WeekendData(weekend=wk, sessions={"FP1": object(), "Q": object()})  # "Q" has no matching DB row
    store_fingerprints(data, db_session)

    stored = db_session.exec(select(Fingerprint).where(Fingerprint.session_id == fp1.id)).all()
    assert len(stored) == 1
    assert stored[0].driver == "LEC"
    assert stored[0].clean_lap_count == 3

    # idempotent re-run (delete + reinsert) leaves exactly one row
    store_fingerprints(data, db_session)
    stored_again = db_session.exec(select(Fingerprint).where(Fingerprint.session_id == fp1.id)).all()
    assert len(stored_again) == 1
