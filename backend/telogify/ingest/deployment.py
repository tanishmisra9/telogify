"""ERS deployment / clipping extraction: per driver, from the fastest representative qualifying
lap, where does the car's electrical deployment run out on the straights.

Reuses the same representative-lap selection as quali_character (fastest clean lap) and the same
distance-aligned telemetry, then runs the pure `detect_clipping` on the speed trace. Stored per
Q/SQ session, idempotently. Race deployment (energy-managed, lap-to-lap) is a later extension.
"""

from sqlmodel import Session as DBSession
from sqlmodel import delete, select

from telogify.analysis.deployment import detect_clipping, summarize_deployment
from telogify.ingest.loader import WeekendData
from telogify.ingest.quali_character import select_representative_laps
from telogify.models import DeploymentTrace, Session

_QUALI_SESSIONS = ("Q", "SQ")


def extract_deployment(session) -> dict[str, dict]:
    """driver -> {constructor, summary, straights} from the driver's fastest representative lap."""
    reps = select_representative_laps(session)
    if len(reps) == 0:
        return {}
    out: dict[str, dict] = {}
    for driver in reps["Driver"].unique():
        drv_laps = reps[reps["Driver"] == driver]
        lap = drv_laps.loc[drv_laps["LapTime"].idxmin()]
        try:
            tel = lap.get_telemetry()
        except Exception:
            continue
        if "Distance" not in tel or len(tel) == 0:
            continue
        runs = detect_clipping(
            tel["Distance"].tolist(),
            tel["Speed"].tolist(),
            tel["Throttle"].tolist(),
            [bool(b) for b in tel["Brake"].tolist()],
        )
        if not runs:
            continue
        out[driver] = {
            "constructor": lap.get("Team"),
            "summary": summarize_deployment(runs),
            "straights": [
                {
                    "start_m": round(r.start_m),
                    "end_m": round(r.end_m),
                    "peak_kmh": round(r.peak_kmh),
                    "peak_at_m": round(r.peak_at_m),
                    "clip_m": round(r.clip_m),
                    "drop_kmh": round(r.drop_kmh),
                    "end_reason": r.end_reason,
                    "is_clip": r.is_clip,
                }
                for r in runs
            ],
        }
    return out


def store_deployment(data: WeekendData, db: DBSession) -> None:
    for code, session in data.sessions.items():
        if code not in _QUALI_SESSIONS:
            continue
        row = db.exec(
            select(Session).where(Session.weekend_id == data.weekend.id, Session.session_type == code)
        ).first()
        if row is None:
            continue
        db.exec(delete(DeploymentTrace).where(DeploymentTrace.session_id == row.id))
        for driver, d in extract_deployment(session).items():
            s = d["summary"]
            db.add(
                DeploymentTrace(
                    session_id=row.id,
                    driver=driver,
                    constructor=d["constructor"],
                    top_speed_kmh=s["top_speed_kmh"],
                    total_clip_m=s["total_clip_m"],
                    max_clip_m=s["max_clip_m"],
                    n_straights=s["n_straights"],
                    n_clips=s["n_clips"],
                    straights_json=d["straights"],
                )
            )
    db.commit()
