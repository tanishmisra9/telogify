import json

from telogify.agent.validation import (
    extract_prose_quantities,
    filter_guardrails_with_recap,
    flag_cross_insight_conflicts,
    flag_false_deployment_superlative,
    flag_false_retirement_causation,
    flag_qualifying_practice_sector_mismatch,
    flag_session_abbreviations,
    flag_unquantified_recap_cause,
    flag_untraceable_numbers,
    flag_untraceable_recap_claims,
    flag_weak_deployment_cluster,
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


def test_flag_false_retirement_causation_china_case():
    text = (
        "Verstappen's retirement traces to a lap-19 turn 6 incident with Pierre Gasly, "
        "when race control noted moving under braking."
    )
    trace = [
        {
            "tool": "get_race_control_events",
            "args": {"driver": "VER"},
            "result": json.dumps(
                [{"lap": 19, "driver": "VER", "kind": "incident", "message": "NOTED - MOVING UNDER BRAKING"}]
            ),
        }
    ]
    issues = flag_false_retirement_causation(text, trace)
    assert len(issues) == 1
    assert "steward-noted" in issues[0]


def test_flag_false_retirement_causation_allows_collision():
    text = "Leclerc retired after a lap-57 collision with Russell."
    trace = [
        {
            "tool": "get_race_control_events",
            "args": {},
            "result": json.dumps(
                [{"lap": 57, "driver": "LEC", "kind": "collision", "message": "COLLISION"}]
            ),
        }
    ]
    assert flag_false_retirement_causation(text, trace) == []


def test_flag_qualifying_practice_sector_mismatch():
    text = (
        "In qualifying Gasly was 0.767 seconds off in sector 2 while hitting 329 km/h on the speed trap."
    )
    trace = [
        {
            "tool": "get_candidate_insights",
            "args": {"n": 10},
            "result": json.dumps(
                [
                    {
                        "rank": 1,
                        "signal_type": "sector_delta",
                        "source_refs": [
                            {
                                "type": "sector_delta",
                                "sector": 2,
                                "constructor": "Alpine",
                                "deficit_s": 0.767,
                            }
                        ],
                    }
                ]
            ),
        }
    ]
    issues = flag_qualifying_practice_sector_mismatch(text, trace)
    assert len(issues) == 1
    assert "practice sector_delta" in issues[0]


def test_flag_false_deployment_superlative():
    text = "Antonelli posted the lowest Q clip in the field at 473.6 metres of ERS clipping."
    trace = [
        {
            "tool": "get_deployment",
            "args": {"session_type": "Q"},
            "result": json.dumps(
                [
                    {"driver": "ANT", "total_clip_m": 473.6, "max_clip_m": 200.0},
                    {"driver": "GAS", "total_clip_m": 470.9, "max_clip_m": 180.0},
                ]
            ),
        }
    ]
    issues = flag_false_deployment_superlative(text, trace)
    assert len(issues) == 1
    assert "470.9" in issues[0]


def test_flag_false_deployment_superlative_shortest_clip():
    text = "Hamilton had the shortest clip among the top-four qualifiers at 186 metres."
    trace = [
        {
            "tool": "get_deployment",
            "args": {"session_type": "Q"},
            "result": json.dumps(
                [
                    {"driver": "HAM", "total_clip_m": 300.0, "max_clip_m": 186.0},
                    {"driver": "NOR", "total_clip_m": 280.0, "max_clip_m": 180.0},
                ]
            ),
        }
    ]
    issues = flag_false_deployment_superlative(text, trace)
    assert len(issues) == 1
    assert "180" in issues[0]


def test_filter_guardrails_with_recap_allows_retirement_lap():
    trace = [
        {
            "tool": "get_weekend_recap",
            "args": {},
            "result": json.dumps(
                {
                    "sessions": {
                        "R": {
                            "present": True,
                            "facts": [
                                {
                                    "kind": "retirement",
                                    "lap": 45,
                                    "drivers": ["VER"],
                                    "text": "Verstappen retired on lap 45 with a coolant leak.",
                                }
                            ],
                        }
                    }
                }
            ),
        }
    ]
    text = "Verstappen retired on lap 45 with a coolant leak."
    phrases = ["on lap 45", "coolant"]
    assert "on lap 45" not in filter_guardrails_with_recap(phrases, text, trace)


def test_flag_untraceable_recap_claims_blocks_unsupported_mechanical():
    trace = [
        {
            "tool": "get_weekend_recap",
            "args": {},
            "result": json.dumps({"sessions": {"R": {"present": True, "facts": []}}}),
        }
    ]
    issues = flag_untraceable_recap_claims("He retired with an engine failure on lap 10.", trace)
    assert any("engine failure" in i for i in issues)


def _recap_trace(fact_text: str) -> list[dict]:
    return [
        {
            "tool": "get_weekend_recap",
            "args": {},
            "result": json.dumps(
                {
                    "sessions": {
                        "R": {
                            "present": True,
                            "facts": [
                                {"kind": "damage", "lap": None, "drivers": ["ANT"], "text": fact_text}
                            ],
                        }
                    }
                }
            ),
        }
    ]


def test_flag_unquantified_recap_cause_rejects_standalone_narrative():
    trace = _recap_trace("broken left-front wheel shield")
    text = "Antonelli's car suffered a broken left-front wheel shield during the race."
    issues = flag_unquantified_recap_cause(text, trace)
    assert len(issues) == 1
    assert "unquantified recap" in issues[0]


def test_flag_unquantified_recap_cause_passes_with_quantified_number():
    trace = _recap_trace("broken left-front wheel shield")
    text = (
        "Antonelli's car lost 0.842 seconds a lap after a broken left-front wheel shield "
        "unbalanced the car for the rest of the race."
    )
    assert flag_unquantified_recap_cause(text, trace) == []


def test_flag_weak_deployment_cluster():
    text = (
        "In qualifying deployment data, Antonelli recorded 1212 metres of clipping, "
        "Leclerc 1160 metres, Russell 1157 metres and Hamilton 1153 metres before the braking zone."
    )
    issues = flag_weak_deployment_cluster(text, [])
    assert len(issues) == 1


def test_flag_session_abbreviations():
    assert flag_session_abbreviations("The quick Q cars were giving up speed.")
    assert not flag_session_abbreviations("The quick qualifying cars were giving up speed.")
