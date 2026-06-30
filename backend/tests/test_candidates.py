from telogify.analysis.candidates import (
    Signal,
    correlate,
    normalize_and_score,
    rank,
)


def _sig(stype, mag, conf, subject):
    return Signal(signal_type=stype, category=stype, magnitude=mag, confidence=conf, subject=subject)


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


def test_rank_is_robustness_descending():
    a = _sig("x", 1.0, 1.0, "A")
    a.robustness = 0.2
    b = _sig("y", 1.0, 1.0, "B")
    b.robustness = 0.9
    assert [s.subject for s in rank([a, b])] == ["B", "A"]
