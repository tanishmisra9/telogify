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

# Gap-to-car-ahead below this is "dirty air": aero wake measurably costs the trailing car lap
# time, so its pace there doesn't reflect the car's true potential (Mirco Bartolozzi/fdataanalysis:
# gap-to-car-ahead is "the best approach, and the simplest one" for isolating clean-air pace;
# asked directly for a threshold, his answer was "0.5s is a good threshold for that").
DIRTY_AIR_GAP_S = 0.5


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
    # Median of only the laps run with a car-ahead gap >= DIRTY_AIR_GAP_S (or no car ahead at
    # all, e.g. the leader). None when no gap data was supplied or no lap qualifies. This is an
    # additional read alongside `median`, not a replacement: the median-anchor ranking this app
    # already validated across 2026 R1-8 is unchanged.
    clean_air_median: float | None = None
    clean_air_n_laps: int = 0


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


def clean_air_laps(
    lap_times: list[float], gaps: list[float | None], threshold: float = DIRTY_AIR_GAP_S
) -> list[float]:
    """Lap times run with no car ahead, or a car ahead at least `threshold` seconds away.

    lap_times and gaps must be the same length and index-aligned (Stint.lap_times_json /
    Stint.gaps_to_car_ahead_json). A None gap means "no car ahead known" (e.g. the leader),
    which counts as clean.
    """
    return [t for t, g in zip(lap_times, gaps) if g is None or g >= threshold]


def box_stats(
    values: list[float],
    compounds: list[str],
    *,
    gaps: list[float | None] | None = None,
) -> BoxStats:
    """Compute box-plot statistics over a list of lap times (seconds).

    gaps, if provided, must be index-aligned with values (gap to car ahead per lap) and adds
    the clean_air_median/clean_air_n_laps fields; the ranking-relevant `median` is unaffected.
    """
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

    clean_air_median: float | None = None
    clean_air_n = 0
    if gaps is not None and len(gaps) == len(values):
        clean = clean_air_laps(values, gaps)
        clean_air_n = len(clean)
        if clean:
            clean_air_median = _quantile(sorted(clean), 0.5)

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
        clean_air_median=clean_air_median,
        clean_air_n_laps=clean_air_n,
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
    gaps: list[float | None] = field(default_factory=list)


def _pace_key(row: PaceRow, rank_by: str) -> float:
    return row.stats.median if rank_by == "median" else row.stats.mean


def _build_rows(groups: dict[str, _Group], *, rank_by: str = "median") -> list[PaceRow]:
    rows: list[PaceRow] = []
    for gid, g in groups.items():
        if not g.laps:
            continue
        gaps = g.gaps if len(g.gaps) == len(g.laps) else None
        rows.append(
            PaceRow(
                id=gid,
                label=gid,
                team=g.team,
                stats=box_stats(g.laps, _compound_tags(g.compounds), gaps=gaps),
                gap_to_fastest_s=0.0,
            )
        )
    rows.sort(key=lambda r: _pace_key(r, rank_by))
    if rows:
        fastest = _pace_key(rows[0], rank_by)
        for r in rows:
            r.gap_to_fastest_s = _pace_key(r, rank_by) - fastest
    return rows


def _exclude_first_race_lap(stints: list[dict]) -> list[dict]:
    """Drop the first representative lap from opening stint 1 (lap_start == 1)."""
    out: list[dict] = []
    for st in stints:
        times = list(st.get("lap_times") or [])
        if st.get("stint_number") == 1 and st.get("lap_start") == 1 and times:
            times = times[1:]
        out.append({**st, "lap_times": times})
    return out


def driver_distributions(stints: list[dict]) -> list[PaceRow]:
    """Per-driver PaceRows from a list of stint dicts.

    Each dict must have: driver (str), constructor (str|None), compound (str|None),
    lap_times (list[float]), and optionally gaps_to_car_ahead (list[float|None],
    index-aligned with lap_times) for the clean_air_median stat.
    """
    groups: dict[str, _Group] = {}
    for st in stints:
        driver = st["driver"]
        g = groups.setdefault(driver, _Group(team=st.get("constructor")))
        g.laps.extend(st.get("lap_times") or [])
        g.compounds.append(st.get("compound"))
        g.gaps.extend(st.get("gaps_to_car_ahead") or [])
    return _build_rows(groups)


def constructor_distributions(stints: list[dict]) -> list[PaceRow]:
    """Per-constructor PaceRows from a list of stint dicts."""
    groups: dict[str, _Group] = {}
    for st in stints:
        key = st.get("constructor") or "?"
        g = groups.setdefault(key, _Group(team=st.get("constructor")))
        g.laps.extend(st.get("lap_times") or [])
        g.compounds.append(st.get("compound"))
        g.gaps.extend(st.get("gaps_to_car_ahead") or [])
    return _build_rows(groups)


def chart_driver_distributions(stints: list[dict]) -> list[PaceRow]:
    """Pace spread chart: lap 1 excluded, sorted and gapped by mean pace."""
    groups: dict[str, _Group] = {}
    for st in _exclude_first_race_lap(stints):
        driver = st["driver"]
        g = groups.setdefault(driver, _Group(team=st.get("constructor")))
        g.laps.extend(st.get("lap_times") or [])
        g.compounds.append(st.get("compound"))
    return _build_rows(groups, rank_by="mean")


def chart_constructor_distributions(stints: list[dict]) -> list[PaceRow]:
    """Pace spread chart: lap 1 excluded, sorted and gapped by mean pace."""
    groups: dict[str, _Group] = {}
    for st in _exclude_first_race_lap(stints):
        key = st.get("constructor") or "?"
        g = groups.setdefault(key, _Group(team=st.get("constructor")))
        g.laps.extend(st.get("lap_times") or [])
        g.compounds.append(st.get("compound"))
    return _build_rows(groups, rank_by="mean")


def constructor_median_gaps(stints: list[dict]) -> dict[str, float]:
    """Return {constructor: gap_to_fastest_s} ranked by median pace.

    Used by constructor_index and candidates. The pace spread chart uses
    chart_constructor_distributions (mean-ranked, lap 1 excluded) instead.
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
