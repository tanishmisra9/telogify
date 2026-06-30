from telogify.analysis.constructor_index import (
    CornerScore,
    lap_deficits,
    rank_constructors,
    summarize_constructor,
    weighted_mean,
)


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


def test_lap_deficits_relative_to_fastest():
    deficits = lap_deficits({"McLaren": 90.0, "Ferrari": 90.3, "Williams": 91.1})
    assert deficits["McLaren"] == 0.0
    assert abs(deficits["Ferrari"] - 0.3) < 1e-9
    assert abs(deficits["Williams"] - 1.1) < 1e-9
