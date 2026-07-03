"""Tests for the season-rollup pure functions (aggregate, overall_ranking, confidence).

The DB orchestrator build_season_snapshot is exercised via test_api against the test DB;
these cover the offline math that decides ranking and confidence."""

import pytest

from telogify.analysis.season import (
    _reference_compound,
    _tyre_deg_on_ref,
    aggregate,
    confidence,
    overall_ranking,
)


# --- aggregate -----------------------------------------------------------


def test_aggregate_empty():
    assert aggregate([]) == {"mean": None, "spread": None, "n": 0}
    assert aggregate([None, None]) == {"mean": None, "spread": None, "n": 0}


def test_aggregate_single_round_has_zero_spread():
    a = aggregate([0.5])
    assert a["mean"] == 0.5
    assert a["spread"] == 0.0
    assert a["n"] == 1


def test_aggregate_spread_separates_consistent_from_swingy():
    consistent = aggregate([0.4, 0.5, 0.6])  # mean 0.5, tight
    swingy = aggregate([0.0, 0.5, 1.0])  # same mean 0.5, wide
    assert consistent["mean"] == swingy["mean"] == 0.5
    assert swingy["spread"] > consistent["spread"]


def test_aggregate_ignores_none_but_counts_the_rest():
    a = aggregate([1.0, None, 3.0])
    assert a["n"] == 2
    assert a["mean"] == 2.0


# --- overall_ranking -----------------------------------------------------


def test_overall_ranking_blend_orders_by_weighted_deficit():
    # A: best race, worst quali. B: worst race, best quali. With 0.6/0.4, race wins the tie.
    pace = {"A": 0.0, "B": 1.0}
    quali = {"A": 1.0, "B": 0.0}
    ranking = overall_ranking(pace, quali)
    # A score = 0.6*0 + 0.4*1 = 0.4; B score = 0.6*1 + 0.4*0 = 0.6 -> A ranks first.
    assert ranking["A"]["rank"] == 1
    assert ranking["B"]["rank"] == 2
    assert ranking["A"]["score"] < ranking["B"]["score"]


def test_overall_ranking_fastest_race_and_quali_ranks_first():
    pace = {"A": 0.0, "B": 0.5, "C": 1.2}
    quali = {"A": 0.0, "B": 0.3, "C": 0.9}
    ranking = overall_ranking(pace, quali)
    assert ranking["A"]["rank"] == 1
    assert ranking["C"]["rank"] == 3


def test_overall_ranking_team_missing_quali_scored_on_race_alone():
    pace = {"A": 0.0, "B": 1.0}
    quali = {"A": 0.0}  # B has no quali data
    ranking = overall_ranking(pace, quali)
    assert set(ranking) == {"A", "B"}
    assert ranking["A"]["rank"] == 1  # A still fastest, not sunk by B's missing metric


def test_overall_ranking_empty():
    assert overall_ranking({}, {}) == {}


# --- confidence ----------------------------------------------------------


def test_confidence_full_season_is_high():
    assert confidence(9, 10) == "high"


def test_confidence_partial_is_med():
    assert confidence(5, 10) == "med"


def test_confidence_sparse_is_low():
    assert confidence(2, 10) == "low"
    assert confidence(0, 10) == "low"
    assert confidence(1, 0) == "low"


# --- tyre wear on a reference compound -----------------------------------


def test_reference_compound_is_the_most_run_by_laps():
    deg = {
        "A": [("MEDIUM", 0.05, 30), ("SOFT", 0.2, 6)],
        "B": [("MEDIUM", 0.06, 25), ("HARD", 0.04, 20)],
    }
    # MEDIUM: 55 laps, HARD: 20, SOFT: 6 -> MEDIUM
    assert _reference_compound(deg) == "MEDIUM"


def test_reference_compound_empty_is_none():
    assert _reference_compound({}) is None


def test_tyre_deg_uses_only_the_reference_compound():
    # A short 6-lap SOFT outlier at -2.7 must not touch the MEDIUM-based number.
    fits = [("MEDIUM", 0.05, 30), ("MEDIUM", 0.07, 28), ("SOFT", -2.7, 6)]
    assert _tyre_deg_on_ref(fits, "MEDIUM") == pytest.approx(0.06)  # median(0.05, 0.07)


def test_tyre_deg_falls_back_when_no_reference_compound_run():
    fits = [("HARD", 0.10, 20), ("HARD", 0.12, 18)]
    assert _tyre_deg_on_ref(fits, "MEDIUM") == pytest.approx(0.11)  # pooled median fallback


def test_tyre_deg_empty_is_none():
    assert _tyre_deg_on_ref([], "MEDIUM") is None
