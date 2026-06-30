import numpy as np

from telogify.analysis.fingerprints import (
    aggregate_fingerprint,
    corner_features,
    dtw_distance,
)


def test_dtw_distance_identical_is_zero():
    assert dtw_distance([1, 2, 3], [1, 2, 3]) == 0.0


def test_dtw_distance_single_mismatch():
    assert dtw_distance([0, 0, 0], [0, 1, 0]) == 1.0


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
