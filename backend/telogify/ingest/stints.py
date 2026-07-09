"""Stint + pace evolution extraction.

A stint is the run of laps between pit stops on one compound (FastF1 tags each lap
with `Stint` and `Compound`). `lap_times` and `avg_pace` use representative laps only:
out/in laps, inaccurate laps, steward-deleted laps (track limits), and non-green-flag
laps (safety car / VSC) are dropped.
For race / sprint sessions each kept lap is fuel-corrected to an empty-tank reference:

    corrected = raw - fuel_effect * (total_laps - lap_number)

so faster cars aren't artificially penalised for running long opening stints. The
full lap range (including out/in laps) is still recorded for context. `tyre_ages` is
kept aligned index-for-index with `lap_times` (FastF1's `TyreLife`, laps on the current
set) so degradation analysis can regress corrected time against actual tyre age rather
than assuming laps are consecutive.

`summarize_stint` is pure and unit-tested offline.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from statistics import mean

import pandas as pd
from sqlmodel import Session as DBSession
from sqlmodel import delete, select

from telogify.config import settings
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
    gaps_to_car_ahead: list[float | None] = field(default_factory=list)


def compute_gaps_to_car_ahead(all_laps: list[dict]) -> dict[tuple[str, int], float | None]:
    """Gap to the car directly ahead, in seconds, per (driver, lap_number).

    all_laps: dicts with driver, lap_number, position (classified position at the end of
    that lap), and session_time_s (session-clock time the lap finished, comparable across
    drivers). Only meaningful for race/sprint sessions, where FastF1 populates Position.

    The gap is the difference between two drivers' session time at the SAME lap number, so it
    approximates real-world interval at that moment; it is None for the race leader (no car
    ahead) and for any lap missing position/time data for either car. A lapped car's "car ahead"
    is whoever the timing sheet ranked just above it at that lap, which can be off by a lap for
    lapped traffic - a documented simplification, not exact interval timing.
    """
    by_lap: dict[int, list[dict]] = defaultdict(list)
    for lap in all_laps:
        if lap.get("position") is None or lap.get("session_time_s") is None:
            continue
        by_lap[lap["lap_number"]].append(lap)

    out: dict[tuple[str, int], float | None] = {}
    for lap_number, rows in by_lap.items():
        ranked = sorted(rows, key=lambda r: r["position"])
        for i, row in enumerate(ranked):
            key = (row["driver"], lap_number)
            if i == 0:
                out[key] = None
            else:
                out[key] = row["session_time_s"] - ranked[i - 1]["session_time_s"]
    return out


def summarize_stint(
    stint_number: int,
    laps: list[dict],
    *,
    total_laps: int | None = None,
    fuel_effect: float | None = None,
) -> StintSummary:
    """laps: dicts with lap_number, lap_time_s, compound, is_outlap, is_inlap,
    is_accurate, track_status, and optionally tyre_age (laps on the current set) and
    gap_to_car_ahead (seconds, from compute_gaps_to_car_ahead).

    total_laps / fuel_effect: when both are provided, each representative lap is
    corrected to an empty-tank reference time. Pass None for non-race sessions.
    """
    lap_numbers = [lap["lap_number"] for lap in laps]
    compound = next((lap["compound"] for lap in laps if lap.get("compound")), None)

    do_fuel = total_laps is not None and fuel_effect is not None

    rep: list[float] = []
    ages: list[float] = []
    gaps: list[float | None] = []
    for lap in laps:
        if lap["is_outlap"] or lap["is_inlap"]:
            continue
        if not lap["is_accurate"]:
            continue
        if lap.get("deleted"):
            # Time deleted by stewards (usually track limits): illegally fast, not our pace.
            # IsAccurate does not catch this; it only checks timing sync (per FastF1 docs).
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
        gaps.append(lap.get("gap_to_car_ahead"))

    return StintSummary(
        stint_number=stint_number,
        compound=compound,
        lap_start=min(lap_numbers),
        lap_end=max(lap_numbers),
        avg_pace=mean(rep) if rep else None,
        lap_times=rep,
        tyre_ages=ages,
        gaps_to_car_ahead=gaps,
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

    # Whole-session gap-to-car-ahead, computed once from every driver's Position + Time.
    all_laps = [
        {
            "driver": r.Driver,
            "lap_number": int(r.LapNumber),
            "position": int(r.Position) if pd.notna(getattr(r, "Position", None)) else None,
            "session_time_s": r.Time.total_seconds() if pd.notna(r.Time) else None,
        }
        for r in laps.itertuples()
        if pd.notna(r.Driver)
    ]
    gaps_map = compute_gaps_to_car_ahead(all_laps)

    out: dict[str, list[StintSummary]] = {}
    for driver in laps["Driver"].dropna().unique():
        dl = laps[laps["Driver"] == driver]
        stints: list[StintSummary] = []
        for stint_no in sorted(dl["Stint"].dropna().unique()):
            sl = dl[dl["Stint"] == stint_no]
            rows = []
            for r in sl.itertuples():
                track_status = str(r.TrackStatus).strip() if pd.notna(r.TrackStatus) else "1"
                lap_number = int(r.LapNumber)
                rows.append(
                    {
                        "lap_number": lap_number,
                        "lap_time_s": r.LapTime.total_seconds() if pd.notna(r.LapTime) else None,
                        "compound": r.Compound if pd.notna(r.Compound) else None,
                        "is_outlap": pd.notna(r.PitOutTime),
                        "is_inlap": pd.notna(r.PitInTime),
                        "is_accurate": bool(r.IsAccurate),
                        "deleted": bool(pd.notna(getattr(r, "Deleted", False)) and getattr(r, "Deleted", False)),
                        "track_status": track_status,
                        "tyre_age": float(r.TyreLife) if pd.notna(getattr(r, "TyreLife", None)) else None,
                        "gap_to_car_ahead": gaps_map.get((driver, lap_number)),
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


def fuel_effect_for_race(total_laps: int) -> float:
    """Seconds shed per lap-remaining, for a race of this many laps.

    corrected = raw - fuel_effect_for_race(total_laps) * (total_laps - lap_number)

    Burn rate is a flat season assumption (fuel_kg_per_race / total_laps for THIS race), priced
    at fuel_time_cost_s_per_kg. See config.py for the source of both constants.
    """
    return settings.fuel_time_cost_s_per_kg * settings.fuel_kg_per_race / total_laps


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

        is_race = code in ("R", "SPRINT")
        # Count total laps in this session for fuel correction (max LapNumber seen).
        session_laps = session.laps
        total_laps: int | None = None
        fuel_effect: float | None = None
        if is_race and len(session_laps) > 0:
            total_laps = int(session_laps["LapNumber"].max())
            if total_laps > 0:
                fuel_effect = fuel_effect_for_race(total_laps)
            else:
                total_laps = None

        for driver, stints in extract_stints(
            session,
            total_laps=total_laps,
            fuel_effect=fuel_effect,
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
                        gaps_to_car_ahead_json=s.gaps_to_car_ahead,
                    )
                )
    db.commit()
