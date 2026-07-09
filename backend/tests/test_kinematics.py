import numpy as np
import pytest

from telogify.analysis.kinematics import deployment_samples, lateral_acceleration_ms2


def _circular_arc(radius_m: float, speed_ms: float, n: int = 400, duration_s: float = 2.0):
    """x, y (FastF1 1/10-metre units), t for a car circling at constant radius/speed.
    True centripetal acceleration is speed_ms**2 / radius_m."""
    omega = speed_ms / radius_m
    t = np.linspace(0, duration_s, n)
    x = radius_m * np.cos(omega * t) * 10.0
    y = radius_m * np.sin(omega * t) * 10.0
    return x, y, t


def test_lateral_acceleration_matches_known_centripetal_value():
    radius_m, speed_ms = 100.0, 50.0
    x, y, t = _circular_arc(radius_m, speed_ms)
    result = lateral_acceleration_ms2(x.tolist(), y.tolist(), t.tolist())
    expected = speed_ms**2 / radius_m
    # Skip filter edge effects at the boundaries.
    assert result[50:-50].mean() == pytest.approx(expected, rel=0.1)


def test_lateral_acceleration_survives_realistic_position_noise():
    radius_m, speed_ms = 100.0, 50.0
    x, y, t = _circular_arc(radius_m, speed_ms)
    rng = np.random.default_rng(0)
    x_noisy = x + rng.normal(0, 3.0, size=x.shape)  # ~0.3m jitter
    y_noisy = y + rng.normal(0, 3.0, size=y.shape)
    result = lateral_acceleration_ms2(x_noisy.tolist(), y_noisy.tolist(), t.tolist())
    expected = speed_ms**2 / radius_m
    # The low-pass filter keeps this close to true; naive double-differentiation of the same
    # noisy input is off by two-to-three orders of magnitude (see kinematics.py docstring).
    assert result[50:-50].mean() == pytest.approx(expected, rel=0.15)


def test_lateral_acceleration_straight_line_is_near_zero():
    t = np.linspace(0, 2.0, 200)
    x = (t * 50.0) * 10.0
    y = np.zeros_like(t)
    result = lateral_acceleration_ms2(x.tolist(), y.tolist(), t.tolist())
    assert abs(result[20:-20].mean()) < 0.5


def test_deployment_samples_drops_implausible_longitudinal_accel():
    speed = [200.0, 210.0]
    throttle = [100.0, 100.0]
    brake = [False, False]
    long_accel = np.array([5.0, 45.0])  # second is a residual derivative artifact
    lateral_accel = np.array([0.1, 0.1])
    samples = deployment_samples(speed, throttle, brake, long_accel, lateral_accel)
    assert samples == [(200.0, 5.0)]


def test_deployment_samples_filters_full_throttle_no_brake_low_lateral_g():
    speed = [200.0, 210.0, 220.0, 230.0]
    throttle = [100.0, 100.0, 60.0, 100.0]  # index 2 fails full-throttle
    brake = [False, True, False, False]  # index 1 fails no-brake
    long_accel = np.array([5.0, 4.0, 3.0, 2.0])
    lateral_accel = np.array([0.5, 0.5, 0.5, 3.0])  # index 3 fails lateral-g limit
    samples = deployment_samples(speed, throttle, brake, long_accel, lateral_accel)
    assert samples == [(200.0, 5.0)]
