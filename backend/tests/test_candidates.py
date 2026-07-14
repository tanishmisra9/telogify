import pytest

from telogify.analysis.candidates import (
    EXPECTATION_FLOOR,
    OBVIOUSNESS_DISCOUNT,
    Signal,
    correlate,
    expectation_factors,
    linear_regression,
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


def test_linear_regression_recovers_known_line():
    xs = [300.0, 310.0, 320.0, 330.0]
    ys = [90.0, 89.0, 88.0, 87.0]  # exact line: y = -0.1x + 120
    fit = linear_regression(xs, ys)
    assert fit is not None
    slope, intercept = fit
    assert slope == pytest.approx(-0.1)
    assert intercept == pytest.approx(120.0)


def test_linear_regression_none_without_x_spread():
    assert linear_regression([300.0, 300.0, 300.0], [90.0, 89.0, 91.0]) is None


def test_linear_regression_none_with_fewer_than_two_points():
    assert linear_regression([300.0], [90.0]) is None


def test_mine_deployment_excludes_deficits_at_or_below_the_weak_cluster_bar(db_session):
    from telogify.analysis.candidates import _mine_deployment
    from telogify.models import DeploymentTrace, RaceWeekend, Session as SessionRow

    wk = RaceWeekend(year=2026, round=9, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    quali = SessionRow(weekend_id=wk.id, session_type="Q", status="loaded")
    db_session.add(quali)
    db_session.commit()
    db_session.refresh(quali)

    # All three constructors clip on both cars (the consistency gate needs >=2 clippers per
    # team). Ferrari is the field's best (min=40). Williams (min=55) is only 15m behind Ferrari,
    # normal field behaviour; McLaren (min=150) is 110m behind, a genuine deficit.
    rows = [
        DeploymentTrace(session_id=quali.id, driver="LEC", constructor="Ferrari", total_clip_m=40.0, max_clip_m=40.0),
        DeploymentTrace(session_id=quali.id, driver="HAM", constructor="Ferrari", total_clip_m=45.0, max_clip_m=45.0),
        DeploymentTrace(session_id=quali.id, driver="ALB", constructor="Williams", total_clip_m=55.0, max_clip_m=55.0),
        DeploymentTrace(session_id=quali.id, driver="SAI", constructor="Williams", total_clip_m=60.0, max_clip_m=60.0),
        DeploymentTrace(session_id=quali.id, driver="NOR", constructor="McLaren", total_clip_m=150.0, max_clip_m=150.0),
        DeploymentTrace(session_id=quali.id, driver="PIA", constructor="McLaren", total_clip_m=160.0, max_clip_m=160.0),
    ]
    for r in rows:
        db_session.add(r)
    db_session.commit()

    signals = _mine_deployment(db_session, [quali])
    subjects = {s.subject for s in signals}
    assert subjects == {"McLaren"}
