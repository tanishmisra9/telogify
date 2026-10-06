from telogify.compounds import is_known_compound
from telogify.ingest.stints import summarize_stint


def test_is_known_compound_allowlist():
    assert all(is_known_compound(c) for c in ("SOFT", "medium", "Hard", "INTERMEDIATE", "WET", " HARD "))
    assert not any(is_known_compound(c) for c in (None, "", "None", "UNKNOWN", "TEST_UNKNOWN", "nan", "N/A", " ", float("nan")))


def _lap(n, compound):
    return {"lap_number": n, "lap_time_s": 90.0, "compound": compound, "is_outlap": False,
            "is_inlap": False, "is_accurate": True, "deleted": False, "track_status": "1", "tyre_age": float(n)}


def test_summarize_stint_takes_first_known_compound_not_first_truthy():
    # First lap tagged with FastF1's literal "None", later laps real: the stint is HARD, not "None".
    s = summarize_stint(1, [_lap(1, "None"), _lap(2, "HARD"), _lap(3, "HARD")])
    assert s.compound == "HARD"


def test_summarize_stint_all_unknown_is_none():
    assert summarize_stint(1, [_lap(1, "None"), _lap(2, "UNKNOWN")]).compound is None
