"""Best-sector aggregation and sector dominance.

Two related but distinct reads, both built on the same per-session `SectorBest` rows:
  - "best sectors" (practice): each driver's best S1/S2/S3 across every practice session,
    tagged with which session it came from (conditions differ FP1 -> FP3).
  - "sector dominance" (qualifying): which constructor is fastest in each sector and by
    how much, from one session's bests.

Both functions are pure; DB rows are converted to plain dicts by the API layer.
"""

from collections import defaultdict
from dataclasses import dataclass


@dataclass
class DriverBest:
    driver: str
    sector: int
    best_time_s: float
    session_type: str


@dataclass
class SectorDominance:
    sector: int
    constructor: str
    best_time_s: float
    margin_s: float | None  # gap to the second-fastest constructor in this sector


def best_across_sessions(rows: list[dict]) -> list[DriverBest]:
    """rows: dicts with driver, sector, best_time_s, session_type.

    One row per session per driver per sector in; the minimum per (driver, sector) out,
    tagged with the session it came from.
    """
    best: dict[tuple[str, int], DriverBest] = {}
    for r in rows:
        k = (r["driver"], r["sector"])
        if k not in best or r["best_time_s"] < best[k].best_time_s:
            best[k] = DriverBest(
                driver=r["driver"],
                sector=r["sector"],
                best_time_s=r["best_time_s"],
                session_type=r["session_type"],
            )
    return list(best.values())


def sector_dominance(rows: list[dict]) -> list[SectorDominance]:
    """rows: dicts with sector, best_time_s, constructor (one row per driver per sector;
    typically the output of `best_across_sessions` enriched with a constructor field, or a
    single qualifying session's driver bests).

    Per sector, ranks constructors by their best driver's time and returns the fastest,
    with the margin to the second-fastest constructor.
    """
    by_sector: dict[int, dict[str, float]] = defaultdict(dict)
    for r in rows:
        constructor = r.get("constructor")
        if constructor is None:
            continue
        cur = by_sector[r["sector"]].get(constructor)
        if cur is None or r["best_time_s"] < cur:
            by_sector[r["sector"]][constructor] = r["best_time_s"]

    out = []
    for sector, by_constructor in by_sector.items():
        ranked = sorted(by_constructor.items(), key=lambda kv: kv[1])
        if not ranked:
            continue
        fastest_constructor, fastest_time = ranked[0]
        margin = ranked[1][1] - fastest_time if len(ranked) > 1 else None
        out.append(
            SectorDominance(
                sector=sector, constructor=fastest_constructor, best_time_s=fastest_time, margin_s=margin
            )
        )
    return sorted(out, key=lambda d: d.sector)


def best_top_speeds(rows: list[dict]) -> list[dict]:
    """rows: dicts with driver, session_type, max_speed_kmh (one row per zone; multiple
    zones/sessions per driver are expected). Returns each driver's single highest top
    speed, tagged with the session it came from.
    """
    best: dict[str, dict] = {}
    for r in rows:
        d = r["driver"]
        if d not in best or r["max_speed_kmh"] > best[d]["max_speed_kmh"]:
            best[d] = {
                "driver": d,
                "max_speed_kmh": r["max_speed_kmh"],
                "session_type": r["session_type"],
            }
    return list(best.values())
