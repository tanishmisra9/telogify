"""Tests for telogify.serialize (pure text helpers)."""

from telogify.serialize import format_lap_times, strip_em_dashes


def test_strip_em_dashes_replaces_spaced_em_dash():
    assert strip_em_dashes("Ferrari led the way — then faded") == "Ferrari led the way, then faded"


def test_strip_em_dashes_replaces_unspaced_em_dash():
    assert strip_em_dashes("a—b") == "a, b"


def test_strip_en_dash_to_hyphen():
    assert strip_em_dashes("12–15 cars") == "12-15 cars"


def test_strip_em_dashes_none_and_empty():
    assert strip_em_dashes(None) is None
    assert strip_em_dashes("") == ""


def test_strip_em_dashes_other_unicode_dash_variants():
    assert strip_em_dashes("hold ― then lift") == "hold, then lift"
    assert strip_em_dashes("one ⸺ two") == "one, two"


def test_format_lap_times_converts_whole_laps_to_racing_clock():
    assert (
        format_lap_times("quickest in qualifying at 104.361 seconds, with 0.307 seconds gained")
        == "quickest in qualifying at 1:44.361, with 0.307 seconds gained"
    )
    # just over the minute, so the seconds half needs zero-padding
    assert format_lap_times("its lap was 66.475 seconds") == "its lap was 1:06.475"
    # bare "s" unit form, and multiple laps in one sentence
    assert (
        format_lap_times("66.475 s versus 66.113 seconds")
        == "1:06.475 versus 1:06.113"
    )


def test_format_lap_times_leaves_sector_times_and_gaps_alone():
    # real values from persisted insights: sector times and gaps are genuinely quoted in
    # seconds, so converting them would be wrong, not just ugly
    for text in (
        "its 22.048 s sector was 0.174 s faster than the next-best car",
        "fastest at 40.387 seconds and 0.106 seconds clear",
        "0.205 seconds a lap faster than Charles Leclerc's Ferrari",
        "2.776 seconds off the leader",
    ):
        assert format_lap_times(text) == text


def test_format_lap_times_ignores_non_time_quantities():
    assert format_lap_times("reached 331.0 km/h in qualifying") == "reached 331.0 km/h in qualifying"
    assert format_lap_times("1.19 m/s² versus 1.57 m/s²") == "1.19 m/s² versus 1.57 m/s²"
    assert format_lap_times("ranked 95% of the field") == "ranked 95% of the field"


def test_format_lap_times_is_idempotent_and_handles_empty():
    once = format_lap_times("its lap was 104.361 seconds")
    assert format_lap_times(once) == once
    assert format_lap_times(None) is None
    assert format_lap_times("") == ""
