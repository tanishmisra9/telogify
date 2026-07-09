"""Tests for pure Wikipedia wikitext parsing."""

from pathlib import Path

from telogify.ingest.wikipedia_parse import (
    build_recap_payload,
    extract_facts,
    map_sections_to_sessions,
    protagonist_drivers_from_swings,
    split_wikitext_sections,
    strip_wikitext_noise,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "wikipedia"


def _load(name: str) -> str:
    return (_FIXTURES / name).read_text()


def test_split_wikitext_sections_finds_race_and_qualifying():
    sections = split_wikitext_sections(_load("2026_chinese_gp.wikitext"))
    assert "race" in sections
    assert "qualifying" in sections
    assert "background" in sections


def test_map_sections_to_sessions_china():
    sections = split_wikitext_sections(_load("2026_chinese_gp.wikitext"))
    mapped = map_sections_to_sessions(sections)
    assert "R" in mapped
    assert "Q" in mapped
    assert "coolant" in mapped["R"].lower()


def test_extract_facts_china_retirement():
    sections = split_wikitext_sections(_load("2026_chinese_gp.wikitext"))
    summary, facts = extract_facts(sections["race"])
    assert any(f.kind == "retirement" and f.lap == 45 for f in facts)
    assert any("coolant" in f.text.lower() for f in facts)
    assert summary


def test_extract_facts_skips_championship_blocklist():
    _, facts = extract_facts("He scored his maiden win and moved up in the championship standings.")
    assert facts == []


def test_build_recap_payload_respects_session_types():
    payload = build_recap_payload(
        _load("2026_chinese_gp.wikitext"),
        session_types_present={"Q", "R"},
    )
    assert payload["Q"]["present"] is True
    assert payload["R"]["present"] is True
    assert "SQ" not in payload
    assert any("coolant" in f["text"].lower() for f in payload["R"]["facts"])


def test_build_recap_payload_sprint_weekend():
    payload = build_recap_payload(
        _load("2026_austrian_sprint_gp.wikitext"),
        session_types_present={"SQ", "SPRINT", "Q", "R"},
    )
    assert payload["SQ"]["present"] is True
    assert payload["SPRINT"]["present"] is True
    assert any(f["kind"] == "penalty" for f in payload["SPRINT"]["facts"])
    assert any(f["kind"] == "retirement" for f in payload["R"]["facts"])


def test_strip_wikitext_noise_removes_refs():
    cleaned = strip_wikitext_noise("Verstappen retired.<ref>NOTED</ref>")
    assert "<ref" not in cleaned
    assert "Verstappen retired" in cleaned


def test_extract_facts_british_gp_antonelli_arc():
    text = _load("2026_british_gp_race_excerpt.wikitext")
    protagonists = protagonist_drivers_from_swings({"ANT": -14})
    _, facts = extract_facts(text, session_type="R", protagonist_drivers=protagonists)
    texts = " ".join(f["text"] if isinstance(f, dict) else f.text for f in facts)
    assert "ANT" in str([f.drivers if hasattr(f, "drivers") else f.get("drivers") for f in facts])
    assert any("wheel shield" in (f.text if hasattr(f, "text") else f["text"]).lower() for f in facts)
    assert any("track limits" in (f.text if hasattr(f, "text") else f["text"]).lower() for f in facts)
    assert "bodywork" in texts.lower() or "wheel shield" in texts.lower()


def test_extract_drivers_from_surname():
    from telogify.ingest.wikipedia_parse import _extract_drivers

    assert "ANT" in _extract_drivers("Kimi Antonelli reported a problem with his car on lap 41.")
