"""Tests for the canonical race-pace distribution module (pure, no DB)."""

import pytest

from telogify.analysis.race_pace import (
    BoxStats,
    PaceRow,
    box_stats,
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
