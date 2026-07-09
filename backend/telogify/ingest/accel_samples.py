"""ERS deployment/harvesting sample extraction: per driver, one representative race lap's
full-throttle/no-brake/low-lateral-g (speed, longitudinal accel) points, feeding the season-wide
deployment scatter. Reuses the same representative-lap selection as quali_character/deployment
(fastest representative lap per driver). Race only: this is a race-pace/energy-management story,
not a single qualifying lap.
"""

from sqlmodel import Session as DBSession
from sqlmodel import delete, select

from telogify.analysis.deployment import smoothed_longitudinal_acceleration_ms2
from telogify.analysis.kinematics import deployment_samples, lateral_acceleration_ms2
from telogify.ingest.loader import WeekendData
from telogify.ingest.quali_character import select_representative_laps
from telogify.models import AccelSample, Session

_RACE_SESSIONS = ("R",)


def extract_accel_samples(session) -> dict[str, dict]:
    """driver -> {constructor, points: [(speed_kmh, longitudinal_accel_ms2), ...]}."""
    reps = select_representative_laps(session)
    if len(reps) == 0:
        return {}
    out: dict[str, dict] = {}
    for driver in reps["Driver"].unique():
        drv_laps = reps[reps["Driver"] == driver]
        lap = drv_laps.loc[drv_laps["LapTime"].idxmin()]
        try:
            # Uniform resampling: raw car+position telemetry merges at wildly uneven intervals
            # (0.001s-0.9s observed), and differentiating twice over near-zero dt produces
            # nonsensical accelerations (100s of m/s^2). A fixed-rate grid keeps dt consistent
            # so the low-pass + gradient recipe behaves as designed.
            tel = lap.get_telemetry(frequency=10).add_distance()
        except Exception:
            continue
        if len(tel) == 0 or "X" not in tel.columns or "Y" not in tel.columns or "Time" not in tel.columns:
            continue

        time_s = tel["Time"].dt.total_seconds().tolist()
        speed = tel["Speed"].tolist()
        throttle = tel["Throttle"].tolist()
        brake = [bool(b) for b in tel["Brake"].tolist()]

        long_accel = smoothed_longitudinal_acceleration_ms2(speed, time_s)
        lat_accel = lateral_acceleration_ms2(tel["X"].tolist(), tel["Y"].tolist(), time_s)
        points = deployment_samples(speed, throttle, brake, long_accel, lat_accel)
        if not points:
            continue
        out[driver] = {"constructor": lap.get("Team"), "points": points}
    return out


def store_accel_samples(data: WeekendData, db: DBSession) -> None:
    for code, session in data.sessions.items():
        if code not in _RACE_SESSIONS:
            continue
        row = db.exec(
            select(Session).where(Session.weekend_id == data.weekend.id, Session.session_type == code)
        ).first()
        if row is None:
            continue
        db.exec(delete(AccelSample).where(AccelSample.session_id == row.id))
        for driver, d in extract_accel_samples(session).items():
            db.add(
                AccelSample(
                    session_id=row.id,
                    driver=driver,
                    constructor=d["constructor"],
                    speed_kmh_json=[p[0] for p in d["points"]],
                    longitudinal_accel_ms2_json=[p[1] for p in d["points"]],
                )
            )
    db.commit()
