import json

from telogify.traced_examples import MAX_ROW_FIELDS, example_for, parse_trace

INSIGHT = {
    "year": 2026,
    "round": 1,
    "event_name": "Bahrain Grand Prix",
    "header": "h",
    "explanation_web": "Mercedes were 0.167 seconds per lap behind.",
}


def _trace(*rows, tool="get_constructor_ranking"):
    return [{"tool": tool, "args": {}, "result": json.dumps(list(rows))}]


def test_a_unique_source_leaf_becomes_the_example():
    parsed = parse_trace(_trace({"constructor": "Mercedes", "gap_to_team_ahead_s": 0.16695454545454425}))
    ex = example_for(INSIGHT, parsed)
    assert ex["traced"] == "0.167" and ex["raw"] == "0.16695454545454425"
    assert ex["key"] == "gap_to_team_ahead_s" and ex["tool"] == "get_constructor_ranking"
    assert ex["row"]["constructor"] == "Mercedes"


def test_a_number_that_matches_two_leaves_is_skipped_not_guessed():
    parsed = parse_trace(_trace({"a": 0.167}, {"b": 0.1672}))  # both round to 0.167
    assert example_for(INSIGHT, parsed) is None


def test_a_number_absent_from_the_trace_is_skipped():
    assert example_for(INSIGHT, parse_trace(_trace({"gap": 0.9}))) is None


def test_unparseable_returns_and_candidate_rankings_are_ignored():
    trace = [
        {"tool": "get_x", "args": {}, "result": "not json"},
        {"tool": "get_x", "args": {}, "result": None},
    ] + _trace({"magnitude": 0.167}, tool="get_candidate_insights")
    assert parse_trace(trace) == []
    assert example_for(INSIGHT, parse_trace(trace)) is None


def test_row_excerpt_is_capped_but_always_keeps_the_matched_key():
    row = {f"f{i}": i for i in range(20)}
    row["target_s"] = 0.167
    ex = example_for(INSIGHT, parse_trace(_trace(row)))
    assert len(ex["row"]) == MAX_ROW_FIELDS and "target_s" in ex["row"]


def test_a_leaf_whose_key_names_a_different_unit_is_not_a_source():
    ins = {**INSIGHT, "explanation_web": "They were 0.25 seconds slower."}
    assert example_for(ins, parse_trace(_trace({"qualifying_gap_pct": 0.25}))) is None
    assert example_for(ins, parse_trace(_trace({"race_pace_gap_s": 0.25}))) is not None


def test_a_whole_number_figure_is_never_matched_to_an_unrelated_integer():
    ins = {**INSIGHT, "explanation_web": "About 3 seconds slower."}
    assert example_for(ins, parse_trace(_trace({"stint": 3}))) is None


def test_bare_numbers_without_a_unit_are_not_candidates():
    ins = {**INSIGHT, "explanation_web": "He started 3 places back."}
    assert example_for(ins, parse_trace(_trace({"grid": 3}))) is None
