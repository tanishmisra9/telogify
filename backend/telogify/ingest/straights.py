"""Straight-line + trap speed extraction, aligned to physical track location.

Zones are the gaps between consecutive corners (circuit geometry is the same for every
driver), so `drs_zone_id` means the same piece of track for all drivers and cross-driver
comparison is valid. For each driver's fastest clean lap we read the max and end-of-zone
(trap) speed in each gap window. `zone_windows` and `speed_in_zone` are pure and tested.
"""

from dataclasses import dataclass

from sqlmodel import Session as DBSession
from sqlmodel import delete, select

from telogify.ingest.loader import WeekendData
from telogify.ingest.segment import get_corners, select_clean_laps
from telogify.models import Session, StraightSegment

# Keep the corner braking/exit out of the straight window.
CORNER_MARGIN_M = 50.0


@dataclass(frozen=True)
class StraightSeg:
    drs_zone_id: int
    max_speed_kmh: float
    trap_speed_kmh: float


def zone_windows(
    corner_distances: list[float], lap_length: float, margin: float = CORNER_MARGIN_M
) -> list[tuple[int, list[tuple[float, float]]]]:
    """Inter-corner gap windows keyed by a stable zone id. Zone 0 is the start/finish
    straight (wraps across the line); zones 1..n-1 are the gaps between sorted corners."""
    d = sorted(corner_distances)
    zones: list[tuple[int, list[tuple[float, float]]]] = []
    for i in range(1, len(d)):
        lo, hi = d[i - 1] + margin, d[i] - margin
        if hi > lo:
            zones.append((i, [(lo, hi)]))
    wrap: list[tuple[float, float]] = []
    if lap_length - (d[-1] + margin) > 0:
        wrap.append((d[-1] + margin, lap_length))
    if d[0] - margin > 0:
        wrap.append((0.0, d[0] - margin))
    if wrap:
        zones.append((0, wrap))
    return zones


def speed_in_zone(distance, speed, windows: list[tuple[float, float]]) -> tuple[float, float] | None:
    """(max_speed, trap_speed) within the zone, or None if no samples fall in it.
    Trap speed is the speed at the furthest-along sample (end of the straight)."""
    idxs = [k for k in range(len(distance)) if any(lo <= distance[k] <= hi for lo, hi in windows)]
    if not idxs:
        return None
    mx = max(speed[k] for k in idxs)
    trap_idx = max(idxs, key=lambda k: distance[k])
    return float(mx), float(speed[trap_idx])


def extract_straights(session) -> dict[str, list[StraightSeg]]:
    """Per driver, max + trap speed in each track zone from their fastest clean lap."""
    clean = select_clean_laps(session)
    if len(clean) == 0:
        return {}
    corner_d = [c.distance for c in get_corners(session)]
    if len(corner_d) < 2:
        return {}

    out: dict[str, list[StraightSeg]] = {}
    for driver in clean["Driver"].unique():
        drv_laps = clean[clean["Driver"] == driver]
        lap = drv_laps.loc[drv_laps["LapTime"].idxmin()]
        tel = lap.get_telemetry()
        dist = tel["Distance"].to_numpy()
        spd = tel["Speed"].to_numpy()
        lap_len = float(dist.max())
        segs = []
        for zid, windows in zone_windows(corner_d, lap_len):
            r = speed_in_zone(dist, spd, windows)
            if r is not None:
                segs.append(StraightSeg(drs_zone_id=zid, max_speed_kmh=r[0], trap_speed_kmh=r[1]))
        out[driver] = segs
    return out


def store_straights(data: WeekendData, db: DBSession) -> None:
    for code, session in data.sessions.items():
        row = db.exec(
            select(Session).where(
                Session.weekend_id == data.weekend.id, Session.session_type == code
            )
        ).first()
        if row is None:
            continue
        db.exec(delete(StraightSegment).where(StraightSegment.session_id == row.id))
        for driver, segs in extract_straights(session).items():
            for seg in segs:
                db.add(
                    StraightSegment(
                        session_id=row.id,
                        driver=driver,
                        drs_zone_id=seg.drs_zone_id,
                        max_speed_kmh=seg.max_speed_kmh,
                        trap_speed_kmh=seg.trap_speed_kmh,
                    )
                )
    db.commit()
