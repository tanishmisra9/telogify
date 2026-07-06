from telogify.agent.validation import (
    extract_prose_quantities,
    flag_cross_insight_conflicts,
    flag_untraceable_numbers,
    validate_insights,
)


def test_extract_prose_quantities_finds_speeds_and_gaps():
    text = "The Ferrari hit 342 km/h (212 mph) with a 0.35 s pace gap."
    assert 342.0 in extract_prose_quantities(text)
    assert 212.0 in extract_prose_quantities(text)
    assert 0.35 in extract_prose_quantities(text)


def test_extract_prose_quantities_skips_bare_ordinals():
    assert extract_prose_quantities("finished 21st after starting third") == []


def test_flag_untraceable_numbers_passes_when_in_trace():
    text = "McLaren topped 330.5 km/h on the straight."
    trace = [{"tool": "get_deployment", "args": {}, "result": '{"top_speed_kmh": 330.5}'}]
    assert flag_untraceable_numbers(text, trace) == []


def test_flag_untraceable_numbers_fails_when_missing():
    text = "McLaren topped 330.5 km/h on the straight."
    trace = [{"tool": "get_deployment", "args": {}, "result": '{"top_speed_kmh": 320.0}'}]
    assert flag_untraceable_numbers(text, trace) == ["330.5"]


def test_flag_untraceable_numbers_skips_when_no_trace():
    assert flag_untraceable_numbers("330.5 km/h", []) == []


def test_flag_untraceable_numbers_accepts_rounded_stint_average():
    text = "Leclerc averaged 73.459 seconds per lap on softs."
    trace = [{"tool": "get_stint_summary", "args": {}, "result": '{"avg_pace_s": 73.45858333333333}'}]
    assert flag_untraceable_numbers(text, trace) == []


def test_flag_cross_insight_conflicts_detects_opposing_speed_claims():
    insights = [
        {
            "header": "Ferrari had the slowest top speed",
            "explanation_web": "W1",
            "explanation_email": "E1",
        },
        {
            "header": "Ferrari showed the fastest straight-line speed",
            "explanation_web": "W2",
            "explanation_email": "E2",
        },
        {"header": "H3", "explanation_web": "W3", "explanation_email": "E3"},
    ]
    conflicts = flag_cross_insight_conflicts(insights)
    assert len(conflicts) == 1
    assert "Ferrari" in conflicts[0]


def test_flag_cross_insight_conflicts_allows_session_qualified_difference():
    insights = [
        {
            "header": "Ferrari had the slowest top speed in qualifying",
            "explanation_web": "W1",
            "explanation_email": "E1",
        },
        {
            "header": "Ferrari showed the fastest straight-line speed in the race",
            "explanation_web": "W2",
            "explanation_email": "E2",
        },
        {"header": "H3", "explanation_web": "W3", "explanation_email": "E3"},
    ]
    assert flag_cross_insight_conflicts(insights) == []


def test_validate_insights_merges_number_and_conflict_issues():
    insights = [
        {
            "header": "Ferrari hit 999 km/h",
            "explanation_web": "slowest top speed",
            "explanation_email": "E1",
        },
        {
            "header": "Ferrari fastest straight-line speed",
            "explanation_web": "W2",
            "explanation_email": "E2",
        },
        {"header": "H3", "explanation_web": "W3", "explanation_email": "E3"},
    ]
    flagged = validate_insights(insights, [{"tool": "t", "args": {}, "result": "{}"}])
    assert 1 in flagged
    assert any("999" in issue for issue in flagged[1])
