import json

from telogify.agent.validation import (
    extract_prose_quantities,
    flag_cross_insight_conflicts,
    flag_false_deployment_superlative,
    flag_false_retirement_causation,
    flag_gap_or_accel_in_header,
    flag_qualifying_only_finding,
    flag_qualifying_practice_sector_mismatch,
    flag_results_only_insight,
    flag_session_abbreviations,
    flag_untraceable_numbers,
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


def test_plain_english_sprint_is_not_a_session_code():
    # The uppercase session CODE must flag; the plain English word must not — the retry
    # feedback itself tells the agent to write "the sprint", so flagging it deadlocks the
    # regen loop on sprint weekends (2026 R2 failed 6 straight attempts on this).
    assert flag_session_abbreviations("fastest in SPRINT")
    assert not flag_session_abbreviations("Ferrari was quicker in the sprint than the race.")
    assert not flag_session_abbreviations("Sprint pace told a different story.")
    assert not flag_session_abbreviations("its sprint qualifying lap was 96.5 seconds")


def _quali_candidate_trace():
    return [
        {
            "tool": "get_candidate_insights",
            "args": {"category": "quali_character"},
            "result": json.dumps(
                [
                    {
                        "rank": 1,
                        "category": "quali_character",
                        "signal_type": "quali_top_speed_delta",
                        "magnitude": 8.0,
                        "confidence": 1.0,
                        "source_refs": [
                            {"type": "quali_top_speed_delta", "constructor": "McLaren", "deficit_kmh": 8.0}
                        ],
                    }
                ]
            ),
        },
        {
            "tool": "get_quali_character",
            "args": {},
            "result": json.dumps(
                {
                    "rows": [
                        {"constructor": "McLaren", "top_speed_kmh": 322.0, "drag_label": "lacks efficiency"},
                        {"constructor": "Ferrari", "top_speed_kmh": 330.0, "drag_label": "efficient, low drag"},
                    ],
                    "fastest_corner_number": 8,
                    "sector_dominance": [],
                }
            ),
        },
    ]


def test_flag_qualifying_only_finding_blocks_pure_quali_character_claim():
    trace = _quali_candidate_trace()
    text = "McLaren was 8 km/h down on top speed, at 322 km/h, the field's lowest in qualifying."
    issues = flag_qualifying_only_finding(text, trace)
    assert len(issues) == 1
    assert "qualifying-only" in issues[0]


def test_flag_qualifying_only_finding_blocks_qualifying_lap_deployment_clipping():
    # get_deployment reads the qualifying lap only (per its own docstring): a finding built
    # entirely on it is qualifying-only, even though it's a "deployment" category candidate.
    trace = _quali_candidate_trace() + [
        {
            "tool": "get_deployment",
            "args": {},
            "result": json.dumps([{"driver": "NOR", "constructor": "McLaren", "total_clip_m": 240.5, "max_clip_m": 150.0}]),
        }
    ]
    text = "McLaren's electrical deployment ran out for 240.5 metres before the braking zone."
    issues = flag_qualifying_only_finding(text, trace)
    assert len(issues) == 1
    assert "qualifying-only" in issues[0]


def test_flag_qualifying_only_finding_allows_race_session_deployment_character():
    # _mine_ers_character candidates are session_type="R" (race full-throttle acceleration
    # trace), a genuinely race-sourced deployment finding distinct from Q/SQ clipping.
    trace = _quali_candidate_trace() + [
        {
            "tool": "get_candidate_insights",
            "args": {"category": "deployment"},
            "result": json.dumps(
                [
                    {
                        "rank": 1,
                        "category": "deployment",
                        "signal_type": "ers_deployment_character",
                        "magnitude": 0.038,
                        "confidence": 0.7,
                        "source_refs": [
                            {
                                "type": "ers_deployment_character",
                                "constructor": "McLaren",
                                "harvesting_slope_ms2_per_kmh": -0.115,
                                "session_type": "R",
                            }
                        ],
                    }
                ]
            ),
        }
    ]
    text = "McLaren's race acceleration trace showed a -0.115 harvesting slope through the band."
    assert flag_qualifying_only_finding(text, trace) == []


def test_flag_qualifying_only_finding_allows_qualifying_context_for_a_race_finding():
    trace = _quali_candidate_trace() + [
        {
            "tool": "get_session_results",
            "args": {"session_type": "R"},
            "result": json.dumps([{"position": 4, "driver": "NOR", "gap_to_leader": 12.5}]),
        }
    ]
    # cites a qualifying-sourced number (322 km/h) purely as context, plus a race-only number
    # (12.5s gap) that anchors the actual finding: must NOT be flagged.
    text = "McLaren qualified with a 322 km/h top speed but finished 12.5 seconds off the winner."
    assert flag_qualifying_only_finding(text, trace) == []


def test_flag_qualifying_only_finding_skips_when_no_quali_data_in_trace():
    trace = [{"tool": "get_session_results", "args": {}, "result": "[]"}]
    assert flag_qualifying_only_finding("Some insight with 42 seconds cited.", trace) == []


def test_validate_insights_allow_qualifying_only_flag_scopes_the_check():
    trace = _quali_candidate_trace()
    insights = [
        {
            "team": "McLaren",
            "header": "McLaren lacked top speed",
            "explanation_web": "McLaren was 8 km/h down on top speed, at 322 km/h, the field's lowest.",
            "explanation_email": "McLaren was the slowest car in qualifying.",
        }
    ]
    # Race scope (default): the qualifying-only finding must be caught.
    flagged = validate_insights(insights, trace)
    assert 1 in flagged and any("qualifying-only" in issue for issue in flagged[1])

    # Qualifying-agent scope: the exact same insight is legitimate and must NOT be flagged.
    flagged_quali = validate_insights(insights, trace, allow_qualifying_only=True)
    assert not any("qualifying-only" in issue for issues in flagged_quali.values() for issue in issues)


# --- flag_results_only_insight --------------------------------------------


def _results_only_trace():
    return [
        {
            "tool": "get_session_results",
            "args": {"session_type": "R"},
            "result": json.dumps(
                [
                    {"position": 3, "driver": "HAM", "constructor": "Ferrari", "gap_to_leader": 0.772, "status": "Finished"},
                    {"position": 1, "driver": "LEC", "constructor": "Ferrari", "gap_to_leader": 0.0, "status": "Finished"},
                ]
            ),
        },
        {
            "tool": "get_race_control_events",
            "args": {"driver": "HAM"},
            "result": json.dumps(
                [{"lap": 7, "driver": "HAM", "kind": "penalty", "message": "5 second penalty, false start"}]
            ),
        },
    ]


def test_flag_results_only_insight_blocks_pure_recap():
    trace = _results_only_trace()
    text = (
        "Hamilton's Ferrari finished third, 0.772 seconds behind Charles Leclerc, even after "
        "race control issued a five-second penalty for a false start."
    )
    issues = flag_results_only_insight(text, trace)
    assert len(issues) == 1
    assert "results-only" in issues[0]


def test_flag_results_only_insight_allows_when_paired_with_pace_data():
    trace = _results_only_trace() + [
        {
            "tool": "get_constructor_ranking",
            "args": {},
            "result": json.dumps([{"constructor": "Ferrari", "overall_rank": 2, "race_pace_gap_s": 0.168}]),
        }
    ]
    text = "Hamilton's Ferrari finished third, but the car ranked second on race pace, 0.168 seconds off the fastest."
    assert flag_results_only_insight(text, trace) == []


def test_flag_results_only_insight_skips_when_no_results_data_in_trace():
    trace = [{"tool": "get_constructor_ranking", "args": {}, "result": "[]"}]
    assert flag_results_only_insight("Some insight with 42 seconds cited.", trace) == []


def test_flag_results_only_insight_skips_when_no_quantities_cited():
    trace = _results_only_trace()
    assert flag_results_only_insight("Hamilton finished third behind Leclerc.", trace) == []


def test_validate_insights_catches_results_only_finding():
    trace = _results_only_trace()
    insights = [
        {
            "header": "Hamilton's Ferrari finished third after a penalty",
            "explanation_web": (
                "Hamilton's Ferrari finished third, 0.772 seconds behind Charles Leclerc, "
                "even after a five-second penalty for a false start."
            ),
            "explanation_email": "Hamilton finished third despite a five-second penalty.",
        }
    ]
    flagged = validate_insights(insights, trace)
    assert 1 in flagged and any("results-only" in issue for issue in flagged[1])


# Headers pulled from the user's line-by-line audit of a real gpt-5.5 insight regen. Offenders
# carry a raw pace gap, per-lap delta, or acceleration figure the audit flagged as data-in-header;
# clean headers (including ones with a km/h speed or a bare ordinal/position) must still pass.
_AUDIT_OFFENDER_HEADERS = [
    "Bearman's Haas finished seventh despite a 1.772-second race-pace gap",
    "Ferrari was only 0.135 seconds off Mercedes on race pace",
    "Red Bull Racing fell from 9.733 to 4.088 m/s² as speed built",
    "Antonelli's Mercedes opened the final-stint gap by 0.509 seconds a lap on Piastri's McLaren",
    "Ferrari's race pace was second-best, 0.494 seconds a lap off Mercedes",
    "Alpine's late soft run beat the cars around it by 0.24 seconds per lap",
    "Hamilton's final hard stint was 0.599 seconds a lap quicker than Norris",
    "Mercedes had second-ranked race pace at 0.234 seconds a lap off Ferrari",
]

_AUDIT_CLEAN_HEADERS = [
    "Mercedes paired fastest race pace with 254.9 km/h through turn 2",
    "Haas F1 Team's fifth place had real late-race pace behind it",
    "Aston Martin was tenth on race pace and tenth in acceleration at 250 km/h",
    "Racing Bulls kept the race's strongest acceleration at 250 km/h",
    "Red Bull Racing had the fourth-fastest race pace, but its cars finished eighth and twelfth",
    "Cadillac was eleventh of 11 for race acceleration at 250 km/h",
    "Ferrari's race pace was better than Leclerc's eighth place suggested",
    "Leclerc's Ferrari was much closer to McLaren pace in the sprint than Hamilton's",
    "McLaren kept the strongest race acceleration at 250.0 km/h",
    "Alpine had the quickest final stints among the cars finishing sixth to tenth",
    "Alonso's Aston Martin ran soft tyres from lap 4 to lap 58",
    "Cadillac had the strongest 250 km/h race acceleration, but not the race pace",
    "Leclerc's Ferrari finished eighth with the second-quickest race pace",
    "Antonelli's Mercedes had the fastest final stint among the top four",
    "McLaren held its race acceleration best as speed built",
    "Mercedes had the fastest race pace, but its first-place qualifier finished 15th",
    "Williams held acceleration best at 250 km/h in the race, not overall pace",
    "Antonelli's Mercedes sprint win was backed by the quickest one-stint pace",
    "Audi kept the strongest acceleration at 250 km/h in the race",
]


def test_flag_gap_or_accel_in_header_catches_audited_offenders():
    for header in _AUDIT_OFFENDER_HEADERS:
        assert flag_gap_or_accel_in_header(header), f"expected a flag for: {header!r}"


def test_flag_gap_or_accel_in_header_passes_audited_clean_headers():
    for header in _AUDIT_CLEAN_HEADERS:
        assert flag_gap_or_accel_in_header(header) == [], f"unexpected flag for: {header!r}"


def test_flag_gap_or_accel_in_header_ignores_lap_numbers():
    assert flag_gap_or_accel_in_header("Alonso's Aston Martin ran soft tyres from lap 4 to lap 58") == []


def test_validate_insights_catches_gap_in_header():
    insights = [
        {
            "header": "Ferrari was only 0.135 seconds off Mercedes on race pace",
            "explanation_web": "Ferrari ranked second on race pace, 0.135 seconds per lap behind Mercedes.",
            "explanation_email": "Ferrari was 0.135 seconds off Mercedes on race pace.",
        }
    ]
    flagged = validate_insights(insights, trace=[])
    assert 1 in flagged and any("header:" in issue for issue in flagged[1])
