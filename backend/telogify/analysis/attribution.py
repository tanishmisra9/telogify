"""Corner separation / car-vs-driver attribution.

Operates on persisted fingerprints (M8). The corner performance metric is min_speed
(km/h, higher is faster); `delta_s` stores the min-speed delta between two constructors
at a corner (km/h, despite the legacy column name). car_pct / driver_pct are unit-free.

Three correctness rules, each in a pure tested function:
  1. confidence-weighted mean (not sum) when pooling a driver's compounds
  2. low-sample capping: drop any corner-compound with < 5 clean laps
  3. teammate reliability: cap cross-team confidence when a team lacks two drivers
     whose baseline confidence clears 60%
"""

from collections import defaultdict
from dataclasses import dataclass
from statistics import mean

from sqlmodel import Session as DBSession
from sqlmodel import delete, select

from telogify.models import Attribution, Fingerprint, Session, SessionResult

MIN_CLEAN_LAPS = 5
TARGET_LAPS = 8  # clean laps for full per-driver confidence
TEAMMATE_MIN_CONF = 0.6  # brief: teammate baseline confidence threshold
TEAMMATE_CONF_CAP = 0.5  # multiplier applied when teammate baseline is unreliable

# Corner speed-class bands (km/h, min-speed based). ponytail: tune per circuit family.
LOW_MAX_KMH = 125.0
MID_MAX_KMH = 200.0


@dataclass
class DriverCorner:
    constructor: str
    driver: str
    metric: float  # min_speed km/h, higher = faster
    clean_laps: int


def classify_speed(min_speed_kmh: float) -> str:
    if min_speed_kmh < LOW_MAX_KMH:
        return "low"
    if min_speed_kmh < MID_MAX_KMH:
        return "mid"
    return "high"


def driver_confidence(clean_laps: int) -> float:
    return min(1.0, clean_laps / TARGET_LAPS)


def aggregate_driver_corner(fingerprints: list[tuple[float, int]]) -> tuple[float, int] | None:
    """Rule 1 + Rule 2: confidence-weighted mean of min_speed over a driver's compounds,
    excluding any compound built on fewer than MIN_CLEAN_LAPS clean laps.

    fingerprints: [(min_speed, clean_laps)] -> (weighted_min_speed, total_clean_laps) or None.
    """
    valid = [(m, n) for m, n in fingerprints if m is not None and n >= MIN_CLEAN_LAPS]
    if not valid:
        return None
    total = sum(n for _, n in valid)
    metric = sum(m * n for m, n in valid) / total
    return metric, total


def attribute_corner(
    corner_number: int,
    a_drivers: list[DriverCorner],
    b_drivers: list[DriverCorner],
) -> Attribution | None:
    """Split the corner gap between two constructors into car vs driver, with confidence.

    Drivers below MIN_CLEAN_LAPS are assumed already filtered out upstream.
    """
    if not a_drivers or not b_drivers:
        return None

    car_a = mean(d.metric for d in a_drivers)
    car_b = mean(d.metric for d in b_drivers)
    delta = car_a - car_b  # km/h (stored in delta_s)

    def spread(drivers: list[DriverCorner]) -> float | None:
        if len(drivers) < 2:
            return None
        metrics = [d.metric for d in drivers]
        return max(metrics) - min(metrics)

    spreads = [s for s in (spread(a_drivers), spread(b_drivers)) if s is not None]
    driver_component = mean(spreads) if spreads else 0.0
    car_component = abs(delta)
    denom = car_component + driver_component
    car_pct = car_component / denom if denom > 0 else 1.0
    driver_pct = 1.0 - car_pct

    # Confidence from the thinnest sample across the four drivers.
    min_laps = min(d.clean_laps for d in a_drivers + b_drivers)
    confidence = driver_confidence(min_laps)

    # Rule 3: both teams need two drivers clearing the teammate baseline, else cap.
    def reliable(drivers: list[DriverCorner]) -> bool:
        return len(drivers) >= 2 and all(
            driver_confidence(d.clean_laps) >= TEAMMATE_MIN_CONF for d in drivers
        )

    if not (reliable(a_drivers) and reliable(b_drivers)):
        confidence *= TEAMMATE_CONF_CAP

    speed_class = classify_speed(mean([car_a, car_b]))
    return Attribution(
        session_id=0,  # set by caller
        corner_number=corner_number,
        speed_class=speed_class,
        constructor_a=a_drivers[0].constructor,
        constructor_b=b_drivers[0].constructor,
        delta_s=delta,
        car_pct=car_pct,
        driver_pct=driver_pct,
        confidence=confidence,
    )


# --- DB-side orchestration -------------------------------------------------


def _driver_constructor_map(db: DBSession, session_ids: list[int]) -> dict[str, str]:
    rows = db.exec(
        select(SessionResult).where(SessionResult.session_id.in_(session_ids))
    ).all()
    return {r.driver: r.constructor for r in rows if r.constructor}


def _session_driver_corners(db: DBSession, session_id: int, dc_map: dict[str, str]):
    """{corner_number: [DriverCorner]} for one session, applying rules 1 and 2."""
    fps = db.exec(select(Fingerprint).where(Fingerprint.session_id == session_id)).all()
    # (driver, corner) -> [(min_speed, clean_laps)] across compounds
    by_driver_corner: dict[tuple[str, int], list[tuple[float, int]]] = defaultdict(list)
    for fp in fps:
        by_driver_corner[(fp.driver, fp.corner_number)].append((fp.min_speed, fp.clean_lap_count))

    corners: dict[int, list[DriverCorner]] = defaultdict(list)
    for (driver, corner), entries in by_driver_corner.items():
        constructor = dc_map.get(driver)
        if constructor is None:
            continue
        agg = aggregate_driver_corner(entries)
        if agg is None:
            continue
        metric, laps = agg
        corners[corner].append(DriverCorner(constructor, driver, metric, laps))
    return corners


def store_attributions(weekend_id: int, db: DBSession) -> None:
    sessions = db.exec(select(Session).where(Session.weekend_id == weekend_id)).all()
    session_ids = [s.id for s in sessions]
    dc_map = _driver_constructor_map(db, session_ids)

    for session in sessions:
        db.exec(delete(Attribution).where(Attribution.session_id == session.id))
        corners = _session_driver_corners(db, session.id, dc_map)
        for corner_number, drivers in corners.items():
            by_constructor: dict[str, list[DriverCorner]] = defaultdict(list)
            for d in drivers:
                by_constructor[d.constructor].append(d)
            constructors = sorted(by_constructor)
            for i in range(len(constructors)):
                for j in range(i + 1, len(constructors)):
                    attr = attribute_corner(
                        corner_number,
                        by_constructor[constructors[i]],
                        by_constructor[constructors[j]],
                    )
                    if attr is None:
                        continue
                    attr.session_id = session.id
                    db.add(attr)
    db.commit()
