from telogify.analysis.constructor_index import (
    CornerScore,
    rank_constructors,
    summarize_constructor,
    weighted_mean,
)
from telogify.analysis.race_pace import constructor_median_gaps


def test_weighted_mean_is_not_a_sum():
    assert weighted_mean([(10.0, 1.0), (20.0, 1.0)]) == 15.0
    assert weighted_mean([]) is None
    assert weighted_mean([(5.0, 0.0)]) is None


def test_more_corners_does_not_inflate_score():
    # Same advantage/confidence, but one constructor is represented at 10x more corners.
    few = [CornerScore("high", 5.0, 1.0)]
    many = [CornerScore("high", 5.0, 1.0)] * 10
    assert summarize_constructor(few)["overall"] == summarize_constructor(many)["overall"] == 5.0


def test_confidence_weights_dominate():
    scores = [CornerScore("mid", 10.0, 0.9), CornerScore("mid", -10.0, 0.1)]
    # high-confidence +10 should pull the mean well above zero
    assert summarize_constructor(scores)["mid"] == (10 * 0.9 - 10 * 0.1) / (0.9 + 0.1)


def test_rank_highest_advantage_first_unscored_last():
    ranks = rank_constructors({"McLaren": 4.0, "Ferrari": 1.0, "Sauber": None})
    assert ranks["McLaren"] == 1
    assert ranks["Ferrari"] == 2
    assert ranks["Sauber"] == 3  # no score -> last, not buried by a sparsity bug


def test_constructor_median_gaps_relative_to_fastest():
    """constructor_median_gaps replaces lap_deficits as the canonical ranking metric."""
    stints = [
        {"driver": "VER", "constructor": "Red Bull", "compound": "MEDIUM", "lap_times": [90.0, 90.1, 90.2]},
        {"driver": "LEC", "constructor": "Ferrari", "compound": "MEDIUM", "lap_times": [90.3, 90.4, 90.5]},
        {"driver": "RUS", "constructor": "Mercedes", "compound": "HARD",   "lap_times": [91.0, 91.1, 91.2]},
    ]
    gaps = constructor_median_gaps(stints)
    assert gaps["Red Bull"] == 0.0
    assert abs(gaps["Ferrari"] - 0.3) < 1e-9
    assert abs(gaps["Mercedes"] - 1.0) < 1e-9
