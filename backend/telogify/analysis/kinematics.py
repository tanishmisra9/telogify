"""Position-derived kinematics: lateral acceleration from track position, and the
full-throttle/no-brake/low-lateral-g data selection Mirco Bartolozzi (fdataanalysis) uses to
isolate ERS deployment/harvesting from raw speed x longitudinal-acceleration telemetry.

FastF1 exposes no acceleration channel of either axis (only Speed/RPM/Gear/Throttle/Brake/DRS),
so lateral acceleration has to be derived from position (X, Y) via curvature x speed^2. Raw
position samples are noisy, and curvature needs two derivatives, which amplifies that noise
badly - so X and Y are low-pass filtered before differentiating, the same forward-backward RC
filter used to smooth longitudinal acceleration in deployment.py.

Pure and unit-tested offline.
"""

import numpy as np

FULL_THROTTLE_PCT = 98.0
LATERAL_ACCEL_LIMIT_MS2 = 2.0
FILTER_CUTOFF_HZ = 1.5
# No production F1 car sustains longitudinal acceleration beyond this under power; a value past
# it is a residual telemetry/derivative artifact (observed at lap-boundary discontinuities),
# not a real reading, so it is dropped rather than plotted. Same style of defensive clamp as
# deployment.py's MAX_RESIDUAL_MS2.
MAX_PLAUSIBLE_LONGITUDINAL_ACCEL_MS2 = 20.0


def _lowpass(values: np.ndarray, sample_dt: float, cutoff_hz: float = FILTER_CUTOFF_HZ) -> np.ndarray:
    if len(values) < 2 or sample_dt <= 0:
        return values.astype(float).copy()
    rc = 1.0 / (2.0 * np.pi * cutoff_hz)
    alpha = sample_dt / (rc + sample_dt)
    fwd = np.empty_like(values, dtype=float)
    fwd[0] = values[0]
    for i in range(1, len(values)):
        fwd[i] = alpha * values[i] + (1.0 - alpha) * fwd[i - 1]
    bwd = np.empty_like(fwd)
    bwd[-1] = fwd[-1]
    for i in range(len(fwd) - 2, -1, -1):
        bwd[i] = alpha * fwd[i] + (1.0 - alpha) * bwd[i + 1]
    return bwd


def lateral_acceleration_ms2(x: list[float], y: list[float], time_s: list[float]) -> np.ndarray:
    """Centripetal acceleration (m/s^2) from position curvature x speed^2.

    x, y: track position (any consistent unit; FastF1 gives 1/10 metre from 2020+, converted
    to metres here). time_s: session time in seconds, same length as x/y.
    """
    xa = np.asarray(x, dtype=float) / 10.0  # FastF1 position units are 1/10 metre
    ya = np.asarray(y, dtype=float) / 10.0
    ta = np.asarray(time_s, dtype=float)
    if len(xa) < 3:
        return np.zeros(len(xa))

    dt = np.diff(ta)
    dt = dt[dt > 0]
    sample_dt = float(np.median(dt)) if len(dt) else 0.1

    xs = _lowpass(xa, sample_dt)
    ys = _lowpass(ya, sample_dt)

    dx = np.gradient(xs, ta)
    dy = np.gradient(ys, ta)
    ddx = np.gradient(dx, ta)
    ddy = np.gradient(dy, ta)

    speed_sq = dx * dx + dy * dy
    denom = np.maximum(speed_sq, 1e-6) ** 1.5
    curvature = np.abs(dx * ddy - dy * ddx) / denom
    return curvature * speed_sq


def deployment_samples(
    speed_kmh: list[float],
    throttle: list[float],
    brake: list[bool],
    longitudinal_accel: np.ndarray,
    lateral_accel: np.ndarray,
) -> list[tuple[float, float]]:
    """(speed_kmh, longitudinal_accel_ms2) pairs matching Mirco's data selection: full throttle,
    no brake, |lateral accel| < LATERAL_ACCEL_LIMIT_MS2 - isolating deployment/harvesting from
    cornering and braking effects."""
    out: list[tuple[float, float]] = []
    n = len(speed_kmh)
    for i in range(n):
        if throttle[i] < FULL_THROTTLE_PCT:
            continue
        if brake[i]:
            continue
        if abs(lateral_accel[i]) >= LATERAL_ACCEL_LIMIT_MS2:
            continue
        if abs(longitudinal_accel[i]) > MAX_PLAUSIBLE_LONGITUDINAL_ACCEL_MS2:
            continue
        out.append((float(speed_kmh[i]), float(longitudinal_accel[i])))
    return out
