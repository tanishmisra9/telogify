"""Season-wide headline stats for the landing page: total laps analysed, total km of
telemetry. Not a new class of number -- laps come straight from Stint.lap_times_json, the
same representative, clean-lap-filtered laps every other analysis function already reads.
"""

from sqlmodel import Session as DBSession
from sqlmodel import select

from telogify.models import RaceWeekend, Session, Stint

# Official circuit length in km, keyed by RaceWeekend.circuit_name (FastF1's event Location,
# e.g. "Melbourne", "Monte Carlo" -- not the full track name). A circuit missing from this
# table just doesn't contribute to total_km (its laps still count toward total_laps); this is
# a static physical-fact table like lib/teamColors.ts on the frontend, not a "hardcoded year".
CIRCUIT_LENGTH_KM: dict[str, float] = {
    "Melbourne": 5.278,
    "Shanghai": 5.451,
    "Suzuka": 5.807,
    "Sakhir": 5.412,
    "Jeddah": 6.174,
    "Miami Gardens": 5.412,
    "Imola": 4.909,
    "Monte Carlo": 3.337,
    "Montréal": 4.361,
    "Barcelona": 4.657,
    "Spielberg": 4.318,
    "Silverstone": 5.891,
    "Budapest": 4.381,
    "Spa-Francorchamps": 7.004,
    "Zandvoort": 4.259,
    "Monza": 5.793,
    "Baku": 6.003,
    "Marina Bay": 4.940,
    "Austin": 5.513,
    "Mexico City": 4.304,
    "São Paulo": 4.309,
    "Las Vegas": 6.201,
    "Lusail": 5.419,
    "Yas Island": 5.281,
    "Madrid": 5.474,
}


def build_season_stats(year: int, db: DBSession) -> dict | None:
    """Total laps analysed and total km of telemetry across every ingested weekend of `year`.
    Returns None when the year has no weekends (same as build_season_snapshot)."""
    weekends = db.exec(select(RaceWeekend).where(RaceWeekend.year == year)).all()
    if not weekends:
        return None

    total_laps = 0
    total_km = 0.0
    for w in weekends:
        session_ids = [
            s.id for s in db.exec(select(Session).where(Session.weekend_id == w.id)).all()
        ]
        stints = db.exec(select(Stint).where(Stint.session_id.in_(session_ids))).all()
        weekend_laps = sum(len(s.lap_times_json) for s in stints)
        total_laps += weekend_laps

        length_km = CIRCUIT_LENGTH_KM.get(w.circuit_name)
        if length_km is not None:
            total_km += weekend_laps * length_km

    return {"year": year, "total_laps": total_laps, "total_km": round(total_km, 1)}
