"""Straight-line + trap speed extraction per DRS zone.

FastF1 car telemetry has no steering channel, so "steering near zero" is realised
via corner geometry: a straight is a contiguous run of samples with throttle above
threshold that lie outside every corner window. `find_straights` is pure and tested;
zone ids are distance-ordered ordinals of the detected straights.
"""

from dataclasses import dataclass

from sqlmodel import Session as DBSession
from sqlmodel import delete, select

from telogify.ingest.loader import WeekendData
from telogify.ingest.segment import corner_windows, get_corners, select_clean_laps
from telogify.models import Session, StraightSegment

THROTTLE_MIN = 95.0
# ponytail: drop blips too short to be a real straight. Tune if a circuit's zones are missed.
MIN_RUN_SAMPLES = 5


@dataclass(frozen=True)
class StraightSeg:
    drs_zone_id: int
    max_speed_kmh: float
    trap_speed_kmh: float


def _in_corner(dist: float, windows: list[tuple[int, float, float]]) -> bool:
    return any(start <= dist <= end for _, start, end in windows)


def find_straights(
    distance,
    speed,
    throttle,
    windows: list[tuple[int, float, float]],
    *,
    throttle_min: float = THROTTLE_MIN,
    min_samples: int = MIN_RUN_SAMPLES,
) -> list[StraightSeg]:
    """Contiguous high-throttle, outside-corner runs -> per-zone max and trap speed."""
    n = len(distance)
    mask = [throttle[i] > throttle_min and not _in_corner(distance[i], windows) for i in range(n)]

    runs: list[tuple[float, float, float]] = []  # (start_distance, max_speed, trap_speed)
    i = 0
    while i < n:
        if not mask[i]:
            i += 1
            continue
        j = i
        while j < n and mask[j]:
            j += 1
        if (j - i) >= min_samples:
            run_speed = [speed[k] for k in range(i, j)]
            runs.append((distance[i], max(run_speed), speed[j - 1]))
        i = j

    runs.sort(key=lambda r: r[0])
    return [
        StraightSeg(drs_zone_id=zid + 1, max_speed_kmh=mx, trap_speed_kmh=trap)
        for zid, (_, mx, trap) in enumerate(runs)
    ]


def extract_straights(session) -> dict[str, list[StraightSeg]]:
    """Per driver, straights from their fastest clean lap."""
    clean = select_clean_laps(session)
    if len(clean) == 0:
        return {}
    windows = corner_windows(get_corners(session))

    out: dict[str, list[StraightSeg]] = {}
    for driver in clean["Driver"].unique():
        drv_laps = clean[clean["Driver"] == driver]
        lap = drv_laps.loc[drv_laps["LapTime"].idxmin()]
        tel = lap.get_telemetry()
        out[driver] = find_straights(
            tel["Distance"].to_numpy(),
            tel["Speed"].to_numpy(),
            tel["Throttle"].to_numpy(),
            windows,
        )
    return out


def store_straights(data: WeekendData, db: DBSession) -> None:
    """Persist straight_segment rows for every loaded session in the weekend."""
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
