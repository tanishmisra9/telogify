"""Tests for telogify.serialize (pure text helpers)."""

from telogify.serialize import strip_em_dashes


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
