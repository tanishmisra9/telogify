from telogify.analysis.candidates import (
    EXPECTATION_FLOOR,
    OBVIOUSNESS_DISCOUNT,
    Signal,
    correlate,
    expectation_factors,
    normalize_and_score,
    rank,
)


def _sig(stype, mag, conf, subject, category=None):
    return Signal(
        signal_type=stype,
        category=category or stype,
        magnitude=mag,
        confidence=conf,
        subject=subject,
    )


def test_robustness_normalized_per_signal_type():
    signals = [
        _sig("corner_delta", 10.0, 1.0, "A"),
        _sig("corner_delta", 5.0, 1.0, "B"),
        _sig("straight_delta", 20.0, 0.5, "C"),  # different units, normalized within its own type
    ]
    normalize_and_score(signals)
    by_type = {s.subject: s.robustness for s in signals}
    assert by_type["A"] == 1.0  # peak of corner_delta
    assert by_type["B"] == 0.5
    assert by_type["C"] == 0.5  # 20/20 * 0.5; not dwarfed by the larger raw corner number


def test_correlation_merges_and_outranks_parts():
    straight = _sig("straight_delta", 12.0, 1.0, "Ferrari")
    swing = _sig("position_swing", 2.0, 1.0, "Ferrari")
    lone = _sig("corner_delta", 8.0, 1.0, "McLaren")
    signals = [straight, swing, lone]
    normalize_and_score(signals)

    merged = correlate(signals)
    combined = next(s for s in merged if s.signal_type == "cross_session")

    assert combined.subject == "Ferrari"
    assert combined.robustness > straight.robustness
    assert combined.robustness > swing.robustness
    # the lone, uncorrelated signal survives unchanged
    assert any(s.signal_type == "corner_delta" for s in merged)
    # the two parts are gone, replaced by the single combined candidate
    assert not any(s.signal_type in ("straight_delta", "position_swing") for s in merged)


def test_no_correlation_without_both_signal_types():
    straight = _sig("straight_delta", 12.0, 1.0, "Williams")
    normalize_and_score([straight])
    merged = correlate([straight])
    assert len(merged) == 1 and merged[0].signal_type == "straight_delta"


def test_results_table_finding_is_discounted():
    # a lone position swing (readable from the results table) is halved; a telemetry
    # finding of equal raw strength keeps its full score and outranks it.
    swing = _sig("position_swing", 4.0, 1.0, "Haas", category="result")
    telemetry = _sig("straight_delta", 20.0, 1.0, "Sauber")
    normalize_and_score([swing, telemetry])
    assert swing.robustness == OBVIOUSNESS_DISCOUNT  # 1.0 * 0.5
    assert telemetry.robustness == 1.0


def test_more_channels_outrank_fewer():
    # a three-channel structural read beats a two-channel one for a different team.
    three = [
        _sig("quali_top_speed_delta", 10.0, 1.0, "Ferrari", category="quali_character"),
        _sig("sector_delta", 0.3, 1.0, "Ferrari", category="sector"),
        _sig("tyre_degradation", 1.2, 1.0, "Ferrari", category="degradation"),
    ]
    two = [
        _sig("quali_top_speed_delta", 10.0, 1.0, "Alpine", category="quali_character"),
        _sig("sector_delta", 0.3, 1.0, "Alpine", category="sector"),
    ]
    signals = three + two
    normalize_and_score(signals)
    ranked = [s for s in rank(correlate(signals)) if s.signal_type == "cross_session"]
    # both subjects merged into cross-channel candidates; the three-channel read ranks first
    assert [s.subject for s in ranked] == ["Ferrari", "Alpine"]
    assert ranked[0].robustness > ranked[1].robustness


def test_expectation_factors_reward_over_and_under_delivery():
    # expected order (season pace) vs actual finish for a 6-team field.
    expected = {"Front": 1, "Mid": 4, "Over": 6, "AsExpected": 5, "Absent": 3}
    actual = {"Front": 5, "Mid": 4, "Over": 1, "AsExpected": 5}  # ranks 1..4 among finishers
    f = expectation_factors(expected, actual)
    # overdeliverer (6 -> 1) and front-team underdeliverer (1 -> 5) both near the top
    assert f["Over"] > 0.8 and f["Front"] > 0.8
    # finished right where its pace ranks it -> damped to the floor
    assert f["AsExpected"] == EXPECTATION_FLOOR
    # a team in only one ordering gets no factor (caller treats it as neutral)
    assert "Absent" not in f


def test_expectation_factor_damps_as_expected_below_overdeliverer():
    as_expected = _sig("straight_delta", 20.0, 1.0, "Backmarker")  # biggest raw gap
    over = _sig("straight_delta", 10.0, 1.0, "Haas")  # half the raw gap
    signals = [as_expected, over]
    normalize_and_score(signals, {"Backmarker": EXPECTATION_FLOOR, "Haas": 1.0})
    assert over.robustness > as_expected.robustness  # story beats raw magnitude
    # no map -> unchanged, magnitude wins (guards the default path)
    normalize_and_score(signals)
    assert as_expected.robustness > over.robustness


def test_rank_is_robustness_descending():
    a = _sig("x", 1.0, 1.0, "A")
    a.robustness = 0.2
    b = _sig("y", 1.0, 1.0, "B")
    b.robustness = 0.9
    assert [s.subject for s in rank([a, b])] == ["B", "A"]


def test_recap_outcome_correlates_with_position_swing():
    swing = _sig("position_swing", 14.0, 1.0, "Mercedes", category="result")
    recap = _sig("recap_outcome", 12.6, 0.9, "Mercedes", category="recap")
    lone = _sig("corner_delta", 8.0, 1.0, "McLaren")
    signals = [swing, recap, lone]
    normalize_and_score(signals)
    merged = correlate(signals)
    combined = next(s for s in merged if s.subject == "Mercedes" and s.signal_type == "cross_session")
    assert combined.robustness > swing.robustness
    assert combined.robustness > recap.robustness
