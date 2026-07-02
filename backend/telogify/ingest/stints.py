"""Stint + pace evolution extraction.

A stint is the run of laps between pit stops on one compound (FastF1 tags each lap
with `Stint` and `Compound`). `lap_times` and `avg_pace` use representative laps only:
out/in laps, inaccurate laps, and non-green-flag laps (safety car / VSC) are dropped.
For race / sprint sessions each kept lap is fuel-corrected to an empty-tank reference:

    corrected = raw - fuel_effect * (total_laps - lap_number)

so faster cars aren't artificially penalised for running long opening stints. The
full lap range (including out/in laps) is still recorded for context. `tyre_ages` is
kept aligned index-for-index with `lap_times` (FastF1's `TyreLife`, laps on the current
set) so degradation analysis can regress corrected time against actual tyre age rather
than assuming laps are consecutive.

`summarize_stint` is pure and unit-tested offline.
"""

from dataclasses import dataclass, field
from statistics import mean

import pandas as pd
from sqlmodel import Session as DBSession
from sqlmodel import delete, select

from telogify.ingest.loader import WeekendData
from telogify.models import Session, Stint

# FastF1 TrackStatus values that represent a green (racing) lap.
# "1" = green flag, "2" = yellow, "4" = SC, "5" = red, "6" = VSC, "7" = VSC ending.
# We keep only "1"; anything else invalidates the lap for pure pace comparison.
GREEN_FLAG = {"1"}


@dataclass
class StintSummary:
    stint_number: int
    compound: str | None
    lap_start: int
    lap_end: int
    avg_pace: float | None
    lap_times: list[float] = field(default_factory=list)
    tyre_ages: list[float] = field(default_factory=list)


def summarize_stint(
    stint_number: int,
    laps: list[dict],
    *,
    total_laps: int | None = None,
    fuel_effect: float | None = None,
) -> StintSummary:
    """laps: dicts with lap_number, lap_time_s, compound, is_outlap, is_inlap,
    is_accurate, track_status, and optionally tyre_age (laps on the current set).

    total_laps / fuel_effect: when both are provided, each representative lap is
    corrected to an empty-tank reference time. Pass None for non-race sessions.
    """
    lap_numbers = [lap["lap_number"] for lap in laps]
    compound = next((lap["compound"] for lap in laps if lap.get("compound")), None)

    do_fuel = total_laps is not None and fuel_effect is not None

    rep: list[float] = []
    ages: list[float] = []
    for lap in laps:
        if lap["is_outlap"] or lap["is_inlap"]:
            continue
        if not lap["is_accurate"]:
            continue
        if lap.get("track_status", "1") not in GREEN_FLAG:
            continue
        t = lap["lap_time_s"]
        if t is None:
            continue
        if do_fuel:
            # Subtract the extra time carried by the remaining fuel load.
            t = t - fuel_effect * (total_laps - lap["lap_number"])
        rep.append(t)
        ages.append(lap.get("tyre_age"))

    return StintSummary(
        stint_number=stint_number,
        compound=compound,
        lap_start=min(lap_numbers),
        lap_end=max(lap_numbers),
        avg_pace=mean(rep) if rep else None,
        lap_times=rep,
        tyre_ages=ages,
    )


def extract_stints(
    session,
    *,
    total_laps: int | None = None,
    fuel_effect: float | None = None,
) -> dict[str, list[StintSummary]]:
    laps = session.laps
    if len(laps) == 0:
        return {}

    out: dict[str, list[StintSummary]] = {}
    for driver in laps["Driver"].dropna().unique():
        dl = laps[laps["Driver"] == driver]
        stints: list[StintSummary] = []
        for stint_no in sorted(dl["Stint"].dropna().unique()):
            sl = dl[dl["Stint"] == stint_no]
            rows = []
            for r in sl.itertuples():
                track_status = str(r.TrackStatus).strip() if pd.notna(r.TrackStatus) else "1"
                rows.append(
                    {
                        "lap_number": int(r.LapNumber),
                        "lap_time_s": r.LapTime.total_seconds() if pd.notna(r.LapTime) else None,
                        "compound": r.Compound if pd.notna(r.Compound) else None,
                        "is_outlap": pd.notna(r.PitOutTime),
                        "is_inlap": pd.notna(r.PitInTime),
                        "is_accurate": bool(r.IsAccurate),
                        "track_status": track_status,
                        "tyre_age": float(r.TyreLife) if pd.notna(getattr(r, "TyreLife", None)) else None,
                    }
                )
            stints.append(
                summarize_stint(
                    int(stint_no),
                    rows,
                    total_laps=total_laps,
                    fuel_effect=fuel_effect,
                )
            )
        out[driver] = stints
    return out


def store_stints(data: WeekendData, db: DBSession, *, fuel_effect: float | None = None) -> None:
    for code, session in data.sessions.items():
        row = db.exec(
            select(Session).where(
                Session.weekend_id == data.weekend.id, Session.session_type == code
            )
        ).first()
        if row is None:
            continue
        db.exec(delete(Stint).where(Stint.session_id == row.id))

        is_race = code in ("R", "SPRINT")
        # Count total laps in this session for fuel correction (max LapNumber seen).
        session_laps = session.laps
        if is_race and fuel_effect and len(session_laps) > 0:
            total_laps = int(session_laps["LapNumber"].max())
        else:
            total_laps = None

        for driver, stints in extract_stints(
            session,
            total_laps=total_laps,
            fuel_effect=fuel_effect if is_race else None,
        ).items():
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
                        tyre_ages_json=s.tyre_ages,
                    )
                )
    db.commit()
