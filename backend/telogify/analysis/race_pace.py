"""Canonical race-pace distributions.

One authoritative computation of box-plot statistics for both driver and
constructor views. `box_stats` mirrors the quantile / IQR-fence logic in the
frontend's paceStats.ts (linear interpolation, 1.5*IQR fences), so the chart
and any backend ranking are provably identical.

Pure functions only; no DB imports here so the module is unit-testable offline.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from statistics import mean


# A car's "pace ceiling": a low quantile of its lap distribution, i.e. the pace it shows when
# pushing rather than managing. Ranking still uses the median (empirically the best single
# anchor across 2026: it ranks the race winner fastest in 7/8 races, only Monaco fails, and no
# lower quantile fixes Monaco without breaking Miami/Spain). The ceiling is a complementary
# read: a comfortable winner who cruised shows a ceiling well below its median.
PACE_CEILING_QUANTILE = 0.10


@dataclass
class BoxStats:
    mean: float
    median: float
    q1: float
    q3: float
    whisker_low: float
    whisker_high: float
    outliers: list[float]
    n_laps: int
    compounds: list[str]
    pace_ceiling: float


@dataclass
class PaceRow:
    id: str
    label: str
    team: str | None
    stats: BoxStats
    gap_to_fastest_s: float


def _quantile(sorted_vals: list[float], p: float) -> float:
    """Linear-interpolation quantile matching paceStats.ts."""
    n = len(sorted_vals)
    if n == 0:
        raise ValueError("empty list")
    idx = (n - 1) * p
    lo = int(idx)
    hi = lo + 1
    if hi >= n:
        return sorted_vals[lo]
    frac = idx - lo
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac


def box_stats(values: list[float], compounds: list[str]) -> BoxStats:
    """Compute box-plot statistics over a list of lap times (seconds)."""
    if not values:
        raise ValueError("no laps")
    s = sorted(values)
    q1 = _quantile(s, 0.25)
    median = _quantile(s, 0.5)
    q3 = _quantile(s, 0.75)
    iqr = q3 - q1
    fence_lo = q1 - 1.5 * iqr
    fence_hi = q3 + 1.5 * iqr
    in_fence = [v for v in s if fence_lo <= v <= fence_hi]
    whisker_low = in_fence[0] if in_fence else s[0]
    whisker_high = in_fence[-1] if in_fence else s[-1]
    outliers = [v for v in s if v < fence_lo or v > fence_hi]
    return BoxStats(
        mean=mean(s),
        median=median,
        q1=q1,
        q3=q3,
        whisker_low=whisker_low,
        whisker_high=whisker_high,
        outliers=outliers,
        n_laps=len(s),
        compounds=compounds,
        pace_ceiling=_quantile(s, PACE_CEILING_QUANTILE),
    )


# Tag used in the frontend for compound abbreviation.
_COMPOUND_TAG: dict[str, str] = {
    "SOFT": "S",
    "MEDIUM": "M",
    "HARD": "H",
    "INTERMEDIATE": "I",
    "WET": "W",
}


def _compound_tags(raw: list[str | None]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for c in raw:
        tag = _COMPOUND_TAG.get(c or "") if c else None
        if tag and tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


@dataclass
class _Group:
    team: str | None
    laps: list[float] = field(default_factory=list)
    compounds: list[str | None] = field(default_factory=list)


def _build_rows(groups: dict[str, _Group]) -> list[PaceRow]:
    rows: list[PaceRow] = []
    for gid, g in groups.items():
        if not g.laps:
            continue
        rows.append(
            PaceRow(
                id=gid,
                label=gid,
                team=g.team,
                stats=box_stats(g.laps, _compound_tags(g.compounds)),
                gap_to_fastest_s=0.0,
            )
        )
    rows.sort(key=lambda r: r.stats.median)
    if rows:
        fastest = rows[0].stats.median
        for r in rows:
            r.gap_to_fastest_s = r.stats.median - fastest
    return rows


def driver_distributions(stints: list[dict]) -> list[PaceRow]:
    """Per-driver PaceRows from a list of stint dicts.

    Each dict must have: driver (str), constructor (str|None), compound (str|None),
    lap_times (list[float]).
    """
    groups: dict[str, _Group] = {}
    for st in stints:
        driver = st["driver"]
        g = groups.setdefault(driver, _Group(team=st.get("constructor")))
        g.laps.extend(st.get("lap_times") or [])
        g.compounds.append(st.get("compound"))
    return _build_rows(groups)


def constructor_distributions(stints: list[dict]) -> list[PaceRow]:
    """Per-constructor PaceRows from a list of stint dicts."""
    groups: dict[str, _Group] = {}
    for st in stints:
        key = st.get("constructor") or "?"
        g = groups.setdefault(key, _Group(team=st.get("constructor")))
        g.laps.extend(st.get("lap_times") or [])
        g.compounds.append(st.get("compound"))
    return _build_rows(groups)


def constructor_median_gaps(stints: list[dict]) -> dict[str, float]:
    """Return {constructor: gap_to_fastest_s} ranked by median pace.

    Used by constructor_index and candidates to anchor ranking on the same
    metric the chart displays.
    """
    rows = constructor_distributions(stints)
    return {r.id: r.gap_to_fastest_s for r in rows}


def driver_stop_counts(stints: list[dict]) -> dict[str, int]:
    """{driver: stop_count} from stint dicts (each dict needs `driver` and `stint_number`).
    Stop count is stints minus one, so a driver who never pitted shows 0.
    """
    stint_numbers: dict[str, set[int]] = defaultdict(set)
    for st in stints:
        stint_numbers[st["driver"]].add(st["stint_number"])
    return {driver: len(numbers) - 1 for driver, numbers in stint_numbers.items()}


def stop_count_spread(stop_counts: dict[str, int]) -> int:
    """Widest gap between any two drivers' stop counts, 0 if fewer than two drivers."""
    if len(stop_counts) < 2:
        return 0
    values = stop_counts.values()
    return max(values) - min(values)
