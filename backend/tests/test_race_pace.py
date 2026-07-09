"""Tests for the canonical race-pace distribution module (pure, no DB)."""

import pytest

from telogify.analysis.race_pace import (
    BoxStats,
    PaceRow,
    _exclude_first_race_lap,
    box_stats,
    chart_constructor_distributions,
    chart_driver_distributions,
    clean_air_laps,
    constructor_distributions,
    constructor_median_gaps,
    driver_distributions,
    driver_stop_counts,
    stop_count_spread,
)


# --- box_stats -----------------------------------------------------------


def test_box_stats_single_value():
    s = box_stats([90.0], [])
    assert s.median == 90.0
    assert s.q1 == 90.0
    assert s.q3 == 90.0
    assert s.whisker_low == 90.0
    assert s.whisker_high == 90.0
    assert s.outliers == []
    assert s.n_laps == 1


def test_box_stats_empty_raises():
    with pytest.raises(ValueError):
        box_stats([], [])


def test_box_stats_symmetric_distribution():
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    s = box_stats(vals, ["M"])
    assert s.median == 3.0
    assert s.q1 == 2.0
    assert s.q3 == 4.0
    assert s.outliers == []
    assert s.compounds == ["M"]
    assert abs(s.pace_ceiling - 1.4) < 1e-9  # q10 of [1..5]: fast-end pace ceiling


def test_box_stats_pace_ceiling_is_at_or_below_median():
    # A "cruising" distribution (many slow management laps, a few fast) has a ceiling well
    # under the median; ranking uses the median, the ceiling exposes the true pace.
    vals = [90.0] * 8 + [85.0, 85.5]  # 8 cruise laps, 2 push laps
    s = box_stats(vals, ["M"])
    assert s.pace_ceiling < s.median


def test_box_stats_outliers_detected():
    # IQR = 1, fences = [0.5, 4.5]; 100 is an outlier
    vals = [1.0, 2.0, 3.0, 4.0, 100.0]
    s = box_stats(vals, [])
    assert 100.0 in s.outliers
    assert s.whisker_high < 100.0


def test_box_stats_matches_paceStats_ts_quantile():
    """Verify linear-interpolation quantile matches the paceStats.ts formula."""
    # For [90, 91, 92, 93]: Q1 at index 0.75 -> 90 + 0.75*(91-90) = 90.75
    vals = [90.0, 91.0, 92.0, 93.0]
    s = box_stats(vals, [])
    assert abs(s.q1 - 90.75) < 1e-9
    assert abs(s.q3 - 92.25) < 1e-9


def test_box_stats_two_lap_median_interpolates():
    s = box_stats([90.0, 92.0], ["S"])
    assert abs(s.median - 91.0) < 1e-9
    assert s.compounds == ["S"]


# --- driver_distributions / constructor_distributions -------------------


def _make_stints():
    return [
        {"driver": "VER", "constructor": "Red Bull",  "compound": "MEDIUM", "lap_times": [90.0, 90.2, 90.1]},
        {"driver": "HAM", "constructor": "Mercedes",  "compound": "HARD",   "lap_times": [91.0, 91.5, 91.2]},
        {"driver": "LEC", "constructor": "Ferrari",   "compound": "MEDIUM", "lap_times": [90.8, 90.9, 90.7]},
        {"driver": "SAI", "constructor": "Ferrari",   "compound": "HARD",   "lap_times": [91.0, 91.1, 91.0]},
    ]


def test_driver_distributions_sorted_by_median():
    rows = driver_distributions(_make_stints())
    medians = [r.stats.median for r in rows]
    assert medians == sorted(medians)


def test_driver_distributions_gap_to_fastest_zero_for_first():
    rows = driver_distributions(_make_stints())
    assert rows[0].gap_to_fastest_s == 0.0


def test_constructor_distributions_merges_teammates():
    rows = constructor_distributions(_make_stints())
    ferrari = next(r for r in rows if r.id == "Ferrari")
    # Ferrari has 6 laps total (SAI + LEC)
    assert ferrari.stats.n_laps == 6


def test_constructor_median_gaps_fastest_is_zero():
    gaps = constructor_median_gaps(_make_stints())
    assert min(gaps.values()) == 0.0


def test_constructor_median_gaps_ordering():
    gaps = constructor_median_gaps(_make_stints())
    # Red Bull (90.x) should be fastest; Mercedes (91.x) should be slowest here
    assert gaps["Red Bull"] < gaps["Ferrari"] < gaps["Mercedes"]


def test_empty_stints_returns_empty():
    assert driver_distributions([]) == []
    assert constructor_distributions([]) == []
    assert constructor_median_gaps([]) == {}


# --- driver_stop_counts / stop_count_spread ------------------------------


def test_driver_stop_counts_is_stints_minus_one():
    stints = [
        {"driver": "VER", "stint_number": 1},
        {"driver": "VER", "stint_number": 2},
        {"driver": "VER", "stint_number": 3},
        {"driver": "HAM", "stint_number": 1},
    ]
    assert driver_stop_counts(stints) == {"VER": 2, "HAM": 0}


def test_stop_count_spread_widest_gap():
    assert stop_count_spread({"VER": 2, "HAM": 0, "LEC": 3}) == 3


def test_stop_count_spread_needs_two_drivers():
    assert stop_count_spread({"VER": 2}) == 0
    assert stop_count_spread({}) == 0


def test_stints_with_no_lap_times_ignored():
    stints = [
        {"driver": "VER", "constructor": "Red Bull", "compound": None, "lap_times": []},
        {"driver": "LEC", "constructor": "Ferrari",  "compound": "M",  "lap_times": [90.0]},
    ]
    rows = constructor_distributions(stints)
    ids = {r.id for r in rows}
    assert "Red Bull" not in ids
    assert "Ferrari" in ids


# --- chart_distributions (mean-ranked, lap 1 excluded) -------------------


def test_exclude_first_race_lap_drops_opening_lap():
    stints = [
        {"driver": "VER", "stint_number": 1, "lap_start": 1, "lap_times": [100.0, 90.0, 90.0]},
    ]
    filtered = _exclude_first_race_lap(stints)
    assert filtered[0]["lap_times"] == [90.0, 90.0]


def test_exclude_first_race_lap_skips_non_opening_stint():
    stints = [
        {"driver": "VER", "stint_number": 2, "lap_start": 15, "lap_times": [90.0, 90.0]},
    ]
    filtered = _exclude_first_race_lap(stints)
    assert filtered[0]["lap_times"] == [90.0, 90.0]


def test_chart_driver_distributions_sorted_by_mean():
    stints = [
        {"driver": "VER", "constructor": "RB", "compound": "M", "stint_number": 1, "lap_start": 2, "lap_times": [90.0, 90.0, 100.0]},
        {"driver": "HAM", "constructor": "Merc", "compound": "H", "stint_number": 1, "lap_start": 2, "lap_times": [92.0, 92.0, 92.0]},
    ]
    rows_median = driver_distributions(stints)
    rows_chart = chart_driver_distributions(stints)
    assert rows_median[0].id == "VER"
    assert rows_chart[0].id == "HAM"
    assert rows_chart[0].gap_to_fastest_s == 0.0
    means = [r.stats.mean for r in rows_chart]
    assert means == sorted(means)


def test_chart_excludes_lap_one_from_pool():
    stints = [
        {"driver": "VER", "constructor": "RB", "compound": "M", "stint_number": 1, "lap_start": 1, "lap_times": [100.0, 90.0, 90.0]},
    ]
    rows = chart_driver_distributions(stints)
    assert rows[0].stats.n_laps == 2


def test_chart_constructor_distributions_mean_gap():
    stints = [
        {"driver": "VER", "constructor": "RB", "compound": "M", "stint_number": 1, "lap_start": 2, "lap_times": [90.0, 90.0]},
        {"driver": "PER", "constructor": "RB", "compound": "H", "stint_number": 1, "lap_start": 2, "lap_times": [91.0, 91.0]},
    ]
    rows = chart_constructor_distributions(stints)
    assert len(rows) == 1
    assert rows[0].id == "RB"
    assert rows[0].stats.n_laps == 4
    assert rows[0].gap_to_fastest_s == 0.0


def test_compound_tags_dedupe_and_abbreviate():
    stints = [
        {"driver": "VER", "constructor": "Red Bull", "compound": "MEDIUM", "lap_times": [90.0]},
        {"driver": "VER", "constructor": "Red Bull", "compound": "MEDIUM", "lap_times": [90.1]},
        {"driver": "VER", "constructor": "Red Bull", "compound": "HARD",   "lap_times": [90.2]},
    ]
    rows = driver_distributions(stints)
    assert rows[0].stats.compounds == ["M", "H"]


def test_compound_tags_include_intermediate_and_wet():
    stints = [
        {"driver": "VER", "constructor": "Red Bull", "compound": "INTERMEDIATE", "lap_times": [95.0]},
        {"driver": "HAM", "constructor": "Mercedes", "compound": "WET", "lap_times": [96.0]},
    ]
    rows = driver_distributions(stints)
    tags = {r.id: r.stats.compounds for r in rows}
    assert tags["VER"] == ["I"]
    assert tags["HAM"] == ["W"]


def test_box_stats_mean_matches_statistics():
    vals = [90.0, 92.0, 94.0]
    s = box_stats(vals, [])
    assert abs(s.mean - 92.0) < 1e-9


def test_driver_distributions_single_lap_per_driver():
    stints = [{"driver": "VER", "constructor": "Red Bull", "compound": "SOFT", "lap_times": [89.5]}]
    rows = driver_distributions(stints)
    assert len(rows) == 1
    assert rows[0].stats.n_laps == 1
    assert rows[0].stats.median == 89.5


# --- clean-air pace --------------------------------------------------------


def test_clean_air_laps_drops_laps_below_threshold():
    times = [90.0, 90.5, 91.0, 91.5]
    gaps = [None, 0.8, 2.0, 1.5]  # leader (None), dirty air, clean, exactly at threshold
    assert clean_air_laps(times, gaps) == [90.0, 91.0, 91.5]


def test_box_stats_clean_air_median_ignores_dirty_laps():
    values = [90.0, 91.0, 95.0]  # 95.0 is a dirty-air lap, would drag the plain median up
    gaps = [None, 2.0, 0.5]
    s = box_stats(values, [], gaps=gaps)
    assert s.clean_air_n_laps == 2
    assert s.clean_air_median == pytest.approx(90.5)
    # The unfiltered median (ranking-relevant) is unaffected by clean-air filtering.
    assert s.median == 91.0


def test_box_stats_clean_air_median_none_without_gaps():
    s = box_stats([90.0, 91.0], [])
    assert s.clean_air_median is None
    assert s.clean_air_n_laps == 0


def test_driver_distributions_populates_clean_air_median():
    stints = [
        {
            "driver": "VER",
            "constructor": "Red Bull",
            "compound": "SOFT",
            "lap_times": [90.0, 95.0],
            "gaps_to_car_ahead": [None, 0.4],
        }
    ]
    rows = driver_distributions(stints)
    assert rows[0].stats.clean_air_median == 90.0
    assert rows[0].stats.clean_air_n_laps == 1
