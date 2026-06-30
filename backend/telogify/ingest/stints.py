"""Stint + pace evolution extraction.

A stint is the run of laps between pit stops on one compound (FastF1 tags each lap
with `Stint` and `Compound`). `lap_times` and `avg_pace` use representative laps only:
out/in laps and inaccurate laps are dropped, the full lap range is still recorded.
`summarize_stint` is pure and tested.
"""

from dataclasses import dataclass, field
from statistics import mean

import pandas as pd
from sqlmodel import Session as DBSession
from sqlmodel import delete, select

from telogify.ingest.loader import WeekendData
from telogify.models import Session, Stint


@dataclass
class StintSummary:
    stint_number: int
    compound: str | None
    lap_start: int
    lap_end: int
    avg_pace: float | None
    lap_times: list[float] = field(default_factory=list)


def summarize_stint(stint_number: int, laps: list[dict]) -> StintSummary:
    """laps: dicts with lap_number, lap_time_s, compound, is_outlap, is_inlap, is_accurate."""
    lap_numbers = [lap["lap_number"] for lap in laps]
    compound = next((lap["compound"] for lap in laps if lap.get("compound")), None)
    rep = [
        lap["lap_time_s"]
        for lap in laps
        if not lap["is_outlap"]
        and not lap["is_inlap"]
        and lap["is_accurate"]
        and lap["lap_time_s"] is not None
    ]
    return StintSummary(
        stint_number=stint_number,
        compound=compound,
        lap_start=min(lap_numbers),
        lap_end=max(lap_numbers),
        avg_pace=mean(rep) if rep else None,
        lap_times=rep,
    )


def extract_stints(session) -> dict[str, list[StintSummary]]:
    laps = session.laps
    if len(laps) == 0:
        return {}

    out: dict[str, list[StintSummary]] = {}
    for driver in laps["Driver"].dropna().unique():
        dl = laps[laps["Driver"] == driver]
        stints: list[StintSummary] = []
        for stint_no in sorted(dl["Stint"].dropna().unique()):
            sl = dl[dl["Stint"] == stint_no]
            rows = [
                {
                    "lap_number": int(r.LapNumber),
                    "lap_time_s": r.LapTime.total_seconds() if pd.notna(r.LapTime) else None,
                    "compound": r.Compound if pd.notna(r.Compound) else None,
                    "is_outlap": pd.notna(r.PitOutTime),
                    "is_inlap": pd.notna(r.PitInTime),
                    "is_accurate": bool(r.IsAccurate),
                }
                for r in sl.itertuples()
            ]
            stints.append(summarize_stint(int(stint_no), rows))
        out[driver] = stints
    return out


def store_stints(data: WeekendData, db: DBSession) -> None:
    for code, session in data.sessions.items():
        row = db.exec(
            select(Session).where(
                Session.weekend_id == data.weekend.id, Session.session_type == code
            )
        ).first()
        if row is None:
            continue
        db.exec(delete(Stint).where(Stint.session_id == row.id))
        for driver, stints in extract_stints(session).items():
            for s in stints:
                db.add(
                    Stint(
                        session_id=row.id,
                        driver=driver,
                        stint_number=s.stint_number,
                        compound=s.compound,
                        lap_start=s.lap_start,
                        lap_end=s.lap_end,
                        avg_pace=s.avg_pace,
                        lap_times_json=s.lap_times,
                    )
                )
    db.commit()
