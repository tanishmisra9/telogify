"""ERS deployment / clipping detection from a distance-aligned telemetry trace.

Neither FastF1 nor OpenF1 exposes battery state of charge (F1 does not broadcast it), so
deployment is INFERRED from longitudinal acceleration residuals against a per-straight drag
baseline (DDRZ). Each WOT straight fits expected deceleration from its own accelerating
phase; post-peak samples that fall below that curve indicate deploy depletion or
super-clipping. Falls back to acceleration gates (SSDG) when a straight lacks enough
rising-phase data. Pure and unit-tested offline.
"""

from dataclasses import dataclass

import numpy as np

FULL_THROTTLE = 98.0
MIN_STRAIGHT_M = 250.0
MIN_CLIP_M = 40.0
HIGH_SPEED_FRAC = 0.85
HIGH_SPEED_KMH = 280.0
MIN_RISING_SAMPLES = 6
FILTER_CUTOFF_HZ = 1.5
DEPLETION_RESIDUAL_MS2 = -2.0
SUPERCLIP_RESIDUAL_MS2 = -6.5
SSDG_SUPERCLIP_MS2 = -6.0
MAX_RESIDUAL_MS2 = 15.0  # clamp derivative noise
MIN_CLIP_SAMPLES = 3
MIN_SPEED_DROP_KMH = 3.0  # post-peak speed must fall this far below peak to count as clip


@dataclass(frozen=True)
class StraightRun:
    start_m: float
    end_m: float
    peak_kmh: float
    peak_at_m: float
    clip_m: float
    depletion_m: float
    superclip_m: float
    drop_kmh: float
    end_reason: str
    is_clip: bool
    clip_type: str
    clip_severity_ms2: float
    method: str


def _infer_time_s(distance: np.ndarray, speed_kmh: np.ndarray) -> np.ndarray:
    if len(distance) < 2:
        return np.zeros(len(distance))
    v = np.maximum(speed_kmh / 3.6, 1.0)
    dt = np.diff(distance) / v[:-1]
    t = np.zeros(len(distance))
    t[1:] = np.cumsum(dt)
    return t


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


def _acceleration_ms2(speed_kmh: np.ndarray, time_s: np.ndarray) -> np.ndarray:
    v = speed_kmh / 3.6
    return np.gradient(v, time_s)


def smoothed_longitudinal_acceleration_ms2(speed_kmh: list[float], time_s: list[float]) -> np.ndarray:
    """Low-pass-filtered longitudinal acceleration (m/s^2): the same speed-smooth -> gradient ->
    accel-smooth recipe detect_clipping uses, exposed for other consumers (e.g. the season-wide
    ERS deployment scatter, which needs the raw (speed, accel) pairs rather than clip decisions)."""
    sp = np.asarray(speed_kmh, dtype=float)
    t = np.asarray(time_s, dtype=float)
    sample_dt = float(np.median(np.diff(t))) if len(t) > 1 else 0.1
    sp_smooth = _lowpass(sp, sample_dt)
    return _lowpass(_acceleration_ms2(sp_smooth, t), sample_dt)


def _fit_segment_baseline(seg_sp: np.ndarray, seg_accel: np.ndarray) -> np.ndarray | None:
    """Fit a = c0 + c1*v^2 from the rising-speed portion of one WOT straight."""
    rising: list[int] = []
    for k in range(1, len(seg_sp)):
        if seg_sp[k] > seg_sp[k - 1] and seg_sp[k] >= 200.0:
            rising.append(k)
    if len(rising) < MIN_RISING_SAMPLES:
        return None
    v2 = (seg_sp[rising] / 3.6) ** 2
    y = seg_accel[rising]
    slope, intercept = np.polyfit(v2, y, 1)
    if slope >= 0:
        return None
    vv = (seg_sp / 3.6) ** 2
    return intercept + slope * vv


def _classify_residual(residual: float) -> str:
    if residual > DEPLETION_RESIDUAL_MS2:
        return "deploy"
    if residual > SUPERCLIP_RESIDUAL_MS2:
        return "depletion"
    return "superclip"


def _classify_accel_ssdg(accel: float) -> str:
    if accel >= DEPLETION_RESIDUAL_MS2:
        return "deploy"
    if accel >= SSDG_SUPERCLIP_MS2:
        return "depletion"
    return "superclip"


def _states_with_hysteresis(raw_states: list[str]) -> list[str]:
    """Require MIN_CLIP_SAMPLES consecutive clip samples before marking clip."""
    out = list(raw_states)
    i = 0
    while i < len(raw_states):
        if raw_states[i] not in ("depletion", "superclip"):
            i += 1
            continue
        j = i
        while j < len(raw_states) and raw_states[j] in ("depletion", "superclip"):
            j += 1
        if (j - i) < MIN_CLIP_SAMPLES:
            for k in range(i, j):
                out[k] = "deploy"
        i = j
    return out


def _sum_contiguous_clip_m(distance: np.ndarray, states: list[str]) -> tuple[float, float, float]:
    depletion_m = 0.0
    superclip_m = 0.0
    i = 0
    while i < len(states):
        if states[i] not in ("depletion", "superclip"):
            i += 1
            continue
        j = i
        while j < len(states) and states[j] in ("depletion", "superclip"):
            j += 1
        span = distance[j - 1] - distance[i]
        if span > 0:
            kinds = {states[k] for k in range(i, j)}
            if kinds == {"depletion"}:
                depletion_m += span
            elif kinds == {"superclip"}:
                superclip_m += span
            else:
                for k in range(i, j - 1):
                    seg = distance[k + 1] - distance[k]
                    if states[k] == "superclip":
                        superclip_m += seg
                    else:
                        depletion_m += seg
        i = j
    return float(depletion_m), float(superclip_m), float(depletion_m + superclip_m)


def _clip_type(depletion_m: float, superclip_m: float) -> str:
    if depletion_m <= 0 and superclip_m <= 0:
        return ""
    if depletion_m > 0 and superclip_m > 0:
        return "mixed"
    return "depletion" if depletion_m > 0 else "superclip"


def detect_clipping(
    distance: list[float],
    speed: list[float],
    throttle: list[float],
    brake: list[bool],
    time_s: list[float] | None = None,
    gear: list[int] | None = None,
    min_straight_m: float = MIN_STRAIGHT_M,
) -> list[StraightRun]:
    """Find WOT straights; classify deploy depletion / super-clipping via per-straight DDRZ."""
    n = len(distance)
    if n < 3:
        return []

    d = np.asarray(distance, dtype=float)
    sp = np.asarray(speed, dtype=float)
    th = np.asarray(throttle, dtype=float)
    br = np.asarray(brake, dtype=bool)

    t = np.asarray(time_s, dtype=float) if time_s is not None else _infer_time_s(d, sp)
    sample_dt = float(np.median(np.diff(t))) if len(t) > 1 else 0.1

    sp_smooth = _lowpass(sp, sample_dt)
    accel = smoothed_longitudinal_acceleration_ms2(sp, t)

    segments: list[tuple[int, int, str]] = []
    i = 0
    while i < n:
        if th[i] < FULL_THROTTLE or br[i]:
            i += 1
            continue
        j = i
        while j < n and th[j] >= FULL_THROTTLE and not br[j]:
            j += 1
        if (d[j - 1] - d[i]) >= min_straight_m or float(np.max(sp[i:j])) >= 250.0:
            end_reason = "brake" if j < n and br[j] else "lift"
            segments.append((i, j, end_reason))
        i = j if j > i else i + 1

    lap_top = max((float(np.max(sp[s:e])) for s, e, _ in segments), default=0.0)
    runs: list[StraightRun] = []

    for start, end, end_reason in segments:
        seg_d = d[start:end]
        seg_sp = sp_smooth[start:end]
        seg_accel = accel[start:end]
        pk = int(np.argmax(seg_sp))
        peak_kmh = float(seg_sp[pk])
        peak_at_m = float(seg_d[pk])
        drop_kmh = float(seg_sp[pk] - seg_sp[-1])

        expected = _fit_segment_baseline(seg_sp, seg_accel)
        use_ddr = expected is not None
        method = "ddr" if use_ddr else "ssdg"

        raw_states: list[str] = []
        resids: list[float] = []
        for k in range(len(seg_d)):
            if seg_sp[k] < HIGH_SPEED_KMH or k <= pk:
                raw_states.append("deploy")
                resids.append(0.0)
                continue
            if seg_sp[k] > peak_kmh - MIN_SPEED_DROP_KMH:
                raw_states.append("deploy")
                resids.append(0.0)
                continue
            if use_ddr:
                r = float(np.clip(seg_accel[k] - expected[k], -MAX_RESIDUAL_MS2, MAX_RESIDUAL_MS2))
                raw_states.append(_classify_residual(r))
                resids.append(r)
            else:
                a = float(seg_accel[k])
                raw_states.append(_classify_accel_ssdg(a))
                resids.append(a)

        states = _states_with_hysteresis(raw_states)
        depletion_m, superclip_m, clip_m = _sum_contiguous_clip_m(seg_d, states)

        clip_res = [r for s, r in zip(states, resids) if s in ("depletion", "superclip")]
        min_res = min(clip_res) if clip_res else 0.0

        is_clip = peak_kmh >= HIGH_SPEED_FRAC * lap_top and clip_m >= MIN_CLIP_M
        runs.append(
            StraightRun(
                start_m=float(seg_d[0]),
                end_m=float(seg_d[-1]),
                peak_kmh=peak_kmh,
                peak_at_m=peak_at_m,
                clip_m=clip_m,
                depletion_m=depletion_m,
                superclip_m=superclip_m,
                drop_kmh=drop_kmh,
                end_reason=end_reason,
                is_clip=is_clip,
                clip_type=_clip_type(depletion_m, superclip_m),
                clip_severity_ms2=min_res if is_clip else 0.0,
                method=method,
            )
        )

    return runs


def summarize_deployment(runs: list[StraightRun]) -> dict:
    clips = [r for r in runs if r.is_clip]
    return {
        "n_straights": len(runs),
        "n_clips": len(clips),
        "total_clip_m": round(sum(r.clip_m for r in clips), 1),
        "total_depletion_m": round(sum(r.depletion_m for r in clips), 1),
        "total_superclip_m": round(sum(r.superclip_m for r in clips), 1),
        "max_clip_m": round(max((r.clip_m for r in clips), default=0.0), 1),
        "max_clip_severity_ms2": round(
            min((r.clip_severity_ms2 for r in clips), default=0.0), 2
        ),
        "top_speed_kmh": round(max((r.peak_kmh for r in runs), default=0.0), 1),
    }
