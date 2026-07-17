"""Pairwise car comparison: where a lap-time or pace gap between two constructors actually
comes from (cornering by speed class, overall top speed, sector time).

Pure aggregation over data already computed elsewhere (Attribution, StraightSegment,
SectorBest); the DB-side orchestration lives in agent/tools.py. Sign convention throughout:
positive means constructor_a is faster, matching get_corner_delta's existing convention.
"""

from dataclasses import dataclass

# Cross-team single-corner / single-straight gaps beyond these are treated as measurement
# artifacts, matching the TELEMETRY CAVEAT thresholds already given to the insight agent.
CORNER_ARTIFACT_KMH = 15.0
STRAIGHT_ARTIFACT_KMH = 20.0
MIN_CORNER_CONFIDENCE = 0.5


@dataclass
class CornerReading:
    corner_number: int
    speed_class: str | None
    delta_kmh: float  # positive = constructor_a carried more min speed through this corner
    confidence: float | None


def summarize_speed_profile(
    corners: list[CornerReading],
    top_speed_a_kmh: float | None,
    top_speed_b_kmh: float | None,
    sector_times_a_s: dict[int, float],
    sector_times_b_s: dict[int, float],
) -> dict:
    """Aggregate into cornering-by-speed-class, top-speed, and per-sector deltas, dropping
    unreliable single-segment readings. Positive deltas favor constructor_a throughout."""
    confident_corners = [
        c
        for c in corners
        if c.confidence is not None
        and c.confidence >= MIN_CORNER_CONFIDENCE
        and abs(c.delta_kmh) <= CORNER_ARTIFACT_KMH
    ]

    by_class: dict[str, list[CornerReading]] = {}
    for c in confident_corners:
        by_class.setdefault(c.speed_class or "unclassified", []).append(c)

    cornering = [
        {
            "speed_class": cls,
            "avg_delta_kmh": round(sum(c.delta_kmh for c in readings) / len(readings), 3),
            "n_corners": len(readings),
            "corner_numbers": sorted(c.corner_number for c in readings),
        }
        for cls, readings in sorted(by_class.items())
    ]

    top_speed_delta_kmh = None
    if top_speed_a_kmh is not None and top_speed_b_kmh is not None:
        raw = top_speed_a_kmh - top_speed_b_kmh
        if abs(raw) <= STRAIGHT_ARTIFACT_KMH:
            top_speed_delta_kmh = round(raw, 3)

    sector_deltas = [
        {"sector": sector, "delta_s": round(sector_times_a_s[sector] - sector_times_b_s[sector], 3)}
        for sector in sorted(set(sector_times_a_s) & set(sector_times_b_s))
    ]

    return {
        "cornering_by_speed_class": cornering,
        "top_speed_delta_kmh": top_speed_delta_kmh,
        "sector_deltas_s": sector_deltas,
        "confident": bool(cornering or top_speed_delta_kmh is not None or sector_deltas),
    }
