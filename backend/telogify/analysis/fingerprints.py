"""Signature fingerprints + DTW alignment, per driver-corner-compound.

Each clean lap's telemetry is resampled onto a common distance grid across the corner
window (distance is the natural alignment axis for cornering). `dtw_distance` then
measures speed-trace similarity and is used to drop outlier laps (off laps, traffic)
before averaging scalar features. FastF1 has no steering channel, so `steer_at_apex`
is left None rather than invented.
"""

from collections import defaultdict
from dataclasses import dataclass

import numpy as np
from sqlmodel import Session as DBSession
from sqlmodel import delete, select

from telogify.ingest.loader import WeekendData
from telogify.ingest.segment import corner_windows, get_corners, select_clean_laps
from telogify.models import Fingerprint, Session

THROTTLE_ON = 20.0
BRAKE_ON = 0.5
GRID_POINTS = 50
OUTLIER_MULT = 2.0


@dataclass
class FeatureSet:
    min_speed: float | None = None
    brake_point: float | None = None
    trail_brake_dur: float | None = None
    throttle_point: float | None = None
    throttle_ramp: float | None = None
    gear: int | None = None
    steer_at_apex: float | None = None  # no steering channel in FastF1


def dtw_distance(a, b) -> float:
    """Classic O(n*m) dynamic-time-warping cost between two 1D sequences (abs cost)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    n, m = len(a), len(b)
    D = np.full((n + 1, m + 1), np.inf)
    D[0, 0] = 0.0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = abs(a[i - 1] - b[j - 1])
            D[i, j] = cost + min(D[i - 1, j], D[i, j - 1], D[i - 1, j - 1])
    return float(D[n, m])


def resample(distance, values, lo: float, hi: float, n: int = GRID_POINTS):
    """Interpolate `values` onto n evenly spaced points across [lo, hi]."""
    grid = np.linspace(lo, hi, n)
    return grid, np.interp(grid, distance, values)


def corner_features(grid, speed, throttle, brake, gear) -> FeatureSet:
    """Scalar corner signature from one resampled trace. Distances are window-relative."""
    lo = float(grid[0])
    apex = int(np.argmin(speed))
    feat = FeatureSet(min_speed=float(speed[apex]))

    braking = np.where(np.asarray(brake) > BRAKE_ON)[0]
    if len(braking):
        first = int(braking[0])
        feat.brake_point = float(grid[first] - lo)
        feat.trail_brake_dur = float(grid[apex] - grid[first]) if first <= apex else 0.0

    tp_idx = next((k for k in range(apex, len(throttle)) if throttle[k] > THROTTLE_ON), None)
    if tp_idx is not None and tp_idx < len(throttle) - 1:
        feat.throttle_point = float(grid[tp_idx] - lo)
        span = float(grid[-1] - grid[tp_idx])
        if span > 0:
            feat.throttle_ramp = float((throttle[-1] - throttle[tp_idx]) / span)

    if gear is not None:
        feat.gear = int(round(float(gear[apex])))
    return feat


def _mean_features(feats: list[FeatureSet]) -> FeatureSet:
    def avg(attr):
        vals = [getattr(f, attr) for f in feats if getattr(f, attr) is not None]
        return float(np.mean(vals)) if vals else None

    out = FeatureSet(
        min_speed=avg("min_speed"),
        brake_point=avg("brake_point"),
        trail_brake_dur=avg("trail_brake_dur"),
        throttle_point=avg("throttle_point"),
        throttle_ramp=avg("throttle_ramp"),
    )
    gears = [f.gear for f in feats if f.gear is not None]
    out.gear = int(round(float(np.mean(gears)))) if gears else None
    return out


def aggregate_fingerprint(traces: list[dict], *, outlier_mult: float = OUTLIER_MULT):
    """Average per-lap features after DTW-based outlier rejection. -> (FeatureSet, kept_count)."""
    speeds = [np.asarray(t["speed"], float) for t in traces]
    ref = np.median(np.vstack(speeds), axis=0)
    dists = [dtw_distance(s, ref) for s in speeds]
    med = float(np.median(dists)) if dists else 0.0
    kept = [t for t, d in zip(traces, dists) if med == 0.0 or d <= outlier_mult * med] or traces

    feats = [
        corner_features(t["grid"], t["speed"], t["throttle"], t["brake"], t.get("gear"))
        for t in kept
    ]
    return _mean_features(feats), len(kept)


def extract_fingerprints(session, n: int = GRID_POINTS):
    """-> [(driver, corner_number, compound, FeatureSet, clean_lap_count)]."""
    clean = select_clean_laps(session)
    if len(clean) == 0:
        return []
    windows = corner_windows(get_corners(session))

    # Telemetry per lap, grouped by (driver, compound).
    grouped: dict[tuple[str, str], list] = defaultdict(list)
    for _, lap in clean.iterlaps():
        compound = lap["Compound"] if lap["Compound"] else "UNKNOWN"
        try:
            tel = lap.get_telemetry()
        except Exception:
            continue
        grouped[(lap["Driver"], compound)].append(tel)

    results = []
    for (driver, compound), tels in grouped.items():
        for corner_no, lo, hi in windows:
            traces = []
            for tel in tels:
                d = tel["Distance"].to_numpy()
                if d.min() > lo or d.max() < hi:
                    continue
                grid, speed = resample(d, tel["Speed"].to_numpy(), lo, hi, n)
                _, thr = resample(d, tel["Throttle"].to_numpy(), lo, hi, n)
                _, brk = resample(d, tel["Brake"].astype(float).to_numpy(), lo, hi, n)
                _, gr = resample(d, tel["nGear"].astype(float).to_numpy(), lo, hi, n)
                traces.append({"grid": grid, "speed": speed, "throttle": thr, "brake": brk, "gear": gr})
            if not traces:
                continue
            feat, count = aggregate_fingerprint(traces)
            results.append((driver, corner_no, compound, feat, count))
    return results


def store_fingerprints(data: WeekendData, db: DBSession) -> None:
    for code, session in data.sessions.items():
        row = db.exec(
            select(Session).where(
                Session.weekend_id == data.weekend.id, Session.session_type == code
            )
        ).first()
        if row is None:
            continue
        db.exec(delete(Fingerprint).where(Fingerprint.session_id == row.id))
        for driver, corner_no, compound, feat, count in extract_fingerprints(session):
            db.add(
                Fingerprint(
                    session_id=row.id,
                    driver=driver,
                    corner_number=corner_no,
                    brake_point=feat.brake_point,
                    trail_brake_dur=feat.trail_brake_dur,
                    min_speed=feat.min_speed,
                    throttle_point=feat.throttle_point,
                    throttle_ramp=feat.throttle_ramp,
                    steer_at_apex=feat.steer_at_apex,
                    gear=feat.gear,
                    clean_lap_count=count,
                    compound=compound,
                )
            )
    db.commit()
