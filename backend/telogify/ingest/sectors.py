"""Best sector time extraction.

Each driver's best sector 1/2/3 time in a session, straight from FastF1's official
`Sector1Time`/`Sector2Time`/`Sector3Time` lap columns (no telemetry projection needed).
Steward-deleted laps are excluded: a track-limits deletion leaves an illegally fast sector
that would otherwise win as the driver's best.
Stored per session so the analysis layer can decide which sessions to combine (all
practice sessions for the practice "best sectors" block, one Q/SQ session for the
qualifying sector-dominance read) and can always say which session a best came from.

`best_sectors` is pure and unit-tested offline.
"""

from dataclasses import dataclass

import pandas as pd
from sqlmodel import Session as DBSession
from sqlmodel import delete, select

from telogify.ingest.loader import WeekendData
from telogify.models import Session, SectorBest

_SECTOR_COLUMNS = {1: "Sector1Time", 2: "Sector2Time", 3: "Sector3Time"}


@dataclass(frozen=True)
class DriverSectorBest:
    driver: str
    sector: int
    best_time_s: float


def best_sectors(rows: list[dict]) -> list[DriverSectorBest]:
    """rows: dicts with driver, sector1_s, sector2_s, sector3_s (any may be None), and an
    optional `deleted` flag.

    Returns each driver's best (minimum) time per sector, dropping sectors with no valid
    time. Steward-deleted laps are skipped: a lap deleted for track limits has an illegally
    fast sector that would otherwise win as the "best". One row per (driver, sector) that has
    at least one value.
    """
    best: dict[tuple[str, int], float] = {}
    for row in rows:
        if row.get("deleted"):
            continue
        driver = row["driver"]
        for sector, key in ((1, "sector1_s"), (2, "sector2_s"), (3, "sector3_s")):
            t = row.get(key)
            if t is None:
                continue
            k = (driver, sector)
            if k not in best or t < best[k]:
                best[k] = t
    return [
        DriverSectorBest(driver=d, sector=s, best_time_s=t) for (d, s), t in best.items()
    ]


def _sector_seconds(lap_row, column: str) -> float | None:
    val = getattr(lap_row, column, None)
    if val is None or pd.isna(val):
        return None
    return val.total_seconds()


def extract_sector_bests(session) -> list[DriverSectorBest]:
    laps = session.laps
    if len(laps) == 0:
        return []
    rows = [
        {
            "driver": lap.Driver,
            "sector1_s": _sector_seconds(lap, "Sector1Time"),
            "sector2_s": _sector_seconds(lap, "Sector2Time"),
            "sector3_s": _sector_seconds(lap, "Sector3Time"),
            "deleted": bool(pd.notna(getattr(lap, "Deleted", False)) and getattr(lap, "Deleted", False)),
        }
        for lap in laps.itertuples()
    ]
    return best_sectors(rows)


def store_sector_bests(data: WeekendData, db: DBSession) -> None:
    for code, session in data.sessions.items():
        row = db.exec(
            select(Session).where(
                Session.weekend_id == data.weekend.id, Session.session_type == code
            )
        ).first()
        if row is None:
            continue
        db.exec(delete(SectorBest).where(SectorBest.session_id == row.id))
        for best in extract_sector_bests(session):
            db.add(
                SectorBest(
                    session_id=row.id,
                    driver=best.driver,
                    sector=best.sector,
                    best_time_s=best.best_time_s,
                )
            )
    db.commit()
