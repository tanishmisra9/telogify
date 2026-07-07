from telogify.agent.guardrails import flag_unsupported_claims


def test_flags_grid_row_labels():
    assert "front row" in flag_unsupported_claims("Both Ferraris locked out the front row")
    assert "second row" in flag_unsupported_claims("McLaren started from the second row")
    assert "third row" in flag_unsupported_claims("Alpine qualified on the third row")
    # Ordinals are allowed.
    assert flag_unsupported_claims("Leclerc started third and finished eighth") == []


def test_fix_hints_for_grid_row_labels():
    from telogify.agent.guardrails import fix_hints_for_phrases, format_insight_validation_feedback

    hints = fix_hints_for_phrases(["second row"])
    assert any("started third" in h for h in hints)
    assert any("Never" in h and "second row" in h for h in hints)
    feedback = format_insight_validation_feedback({3: ["second row"]})
    assert "slot(s) [3]" in feedback
    assert "started third" in feedback
    assert "explanation_email" in feedback


def test_flags_the_audited_fabrications():
    # The exact failure phrases from the audit must be caught.
    assert flag_unsupported_claims("Antonelli's maiden Grand Prix win") == ["maiden"]
    assert "debut" in flag_unsupported_claims("Cadillac's debut weekend ends in retirement")
    assert "pole to flag" in flag_unsupported_claims("Antonelli led from pole to flag")
    assert "this season" in flag_unsupported_claims("his fourth win this season")


def test_flags_retirement_lap_numbers():
    # These exact phrasings shipped in production (Barcelona round 7) despite the earlier
    # substring-only blocklist, because they weren't literal matches.
    assert "on lap 61" in flag_unsupported_claims("his race ended in retirement on lap 61")
    assert "on lap 37" in flag_unsupported_claims(
        "Fernando Alonso retired on lap 37 having managed a best stint average"
    )
    assert "after just five laps" in flag_unsupported_claims(
        "Lance Stroll was out after just five laps"
    )
    assert "after 10 laps" in flag_unsupported_claims("he retired after 10 laps")


def test_allows_race_control_lap_cites():
    assert flag_unsupported_claims(
        "Charles Leclerc still finished eighth, but race control shows a lap-57 collision with George Russell"
    ) == []
    assert flag_unsupported_claims(
        "Piastri was involved in a collision on lap 16 and took a penalty on lap 23"
    ) == []
    assert flag_unsupported_claims(
        "involved in a collision at turn 1 on lap 57"
    ) == []


def test_flags_overtake_lap_claims():
    assert "on lap 30" in flag_unsupported_claims("Norris passed Piastri on lap 30 on the straight")


def test_flags_sprint_weekend_fabrications():
    assert "clean sweep" in flag_unsupported_claims("Verstappen took a clean sweep of the weekend")
    assert "won the weekend" in flag_unsupported_claims("Norris won the weekend with pace to spare")
    assert "double win" in flag_unsupported_claims("a double win for McLaren")
    assert "pole to flag in the sprint" in flag_unsupported_claims(
        "He led pole to flag in the sprint before finishing third in the race"
    )


def test_flags_setup_inference_from_telemetry():
    # The exact Austrian-GP (round 8) Cadillac overreach: a "two different cars / wing swap"
    # story built on one noisy speed segment, inferring setup we never see.
    assert "two completely different cars" in flag_unsupported_claims(
        "Cadillac ran two completely different cars across the weekend on the straights"
    )
    assert "wing-level swap" in flag_unsupported_claims(
        "the wing-level swap between Saturday and Sunday is one of the biggest in the field"
    )
    assert "wing change" in flag_unsupported_claims("a clear wing change from qualifying to the race")


def test_flags_drs_mentions():
    # DRS channel semantics are unreliable (FastF1), so any DRS claim is unsupported.
    assert flag_unsupported_claims("Verstappen used DRS to close the gap")
    assert flag_unsupported_claims("fastest through the second DRS zone")
    # "address" contains no standalone drs; must not false-fire
    assert flag_unsupported_claims("Hamilton set the fastest final sector") == []


def test_clean_prose_is_not_flagged():
    text = (
        "George Russell converted pole into a controlled win, finishing 1.6 seconds clear. "
        "Ferrari had the second-quickest race pace, 0.22 seconds a lap off Mercedes. "
        "Leclerc qualified second but came home eighth after a four-stop strategy."
    )
    assert flag_unsupported_claims(text) == []


def test_empty_text():
    assert flag_unsupported_claims("") == []
    assert flag_unsupported_claims(None) == []


def test_flags_retirement_causes():
    # We know a car retired, never why; each cause phrase must block.
    assert "crash" in flag_unsupported_claims("Russell retired after a crash at Turn 5")
    assert "mechanical failure" in flag_unsupported_claims("a mechanical failure ended his race")
    assert "engine failure" in flag_unsupported_claims("an engine failure on the main straight")
    assert "puncture" in flag_unsupported_claims("a puncture forced an early stop")
    assert "retired due to" in flag_unsupported_claims("He retired due to a hydraulic leak")


def test_flags_doubled_constructor_possessive():
    assert flag_unsupported_claims("Alpine's Alpine straight-line deficit was the largest")
    assert flag_unsupported_claims("Ferrari's Ferrari ran out of deployment on the back straight")


def test_flags_implausible_kmh_magnitude_backstop():
    # >=31 km/h comparative gaps are blocked; small legit gaps and absolute speeds are not.
    assert flag_unsupported_claims("McLaren was 35 km/h slower through the speed trap")
    assert flag_unsupported_claims("a 42 km/h deficit on the main straight")
    assert flag_unsupported_claims("99 km/h quicker than the field leader")
    assert flag_unsupported_claims("Verstappen hit 331 km/h on the straights") == []
    assert flag_unsupported_claims("Ferrari was 12 km/h slower on the straight") == []


def test_flags_grid_row_labels():
    assert "front row" in flag_unsupported_claims("Both Ferraris locked out the front row")
    assert "second row" in flag_unsupported_claims("McLaren started from the second row")
    assert "third row" in flag_unsupported_claims("Alpine qualified on the third row")


def test_flags_leadership_and_start_lap_events():
    assert "led every lap" in flag_unsupported_claims("Norris led every lap on his way to victory")
    assert "wire to wire" in flag_unsupported_claims("a wire to wire win for Mercedes")
    assert "off the line" in flag_unsupported_claims("Russell got away cleanly off the line")
    assert "turn one" in flag_unsupported_claims("contact at turn one reshaped the order")


def test_flags_career_and_season_framing():
    assert "first win" in flag_unsupported_claims("Antonelli took his first win from pole")
    assert "championship" in flag_unsupported_claims("a championship-defining result for McLaren")
    assert "back-to-back" in flag_unsupported_claims("a back-to-back victory for Red Bull")


def test_collision_from_race_control_is_allowed():
    # Collisions are ingested from race control; the agent may cite them, unlike invented causes.
    assert flag_unsupported_claims(
        "Russell's race was compromised by a lap-57 collision with Verstappen"
    ) == []


def test_plain_ordinals_and_collision_are_allowed():
    assert flag_unsupported_claims("Leclerc started third and finished eighth") == []
    assert flag_unsupported_claims("a collision with Norris at turn 6") == []
    assert "first corner" in flag_unsupported_claims("contact at the first corner")


def test_kmh_backstop_boundary_30_not_flagged():
    assert flag_unsupported_claims("Williams was 30 km/h slower on the straight") == []


def test_flags_completed_lap_count_regex():
    assert "completed 42 laps" in flag_unsupported_claims("He completed 42 laps before stopping")


def test_flags_remaining_retirement_cause_phrases():
    assert "hit the wall" in flag_unsupported_claims("He hit the wall at turn 12")
    assert "gearbox" in flag_unsupported_claims("a gearbox issue ended the run")
    assert "led from start to finish" in flag_unsupported_claims("McLaren led from start to finish")


def test_flags_additional_blocklist_categories():
    assert "newcomer" in flag_unsupported_claims("the newcomer struggled on debut pace")
    assert "lights to flag" in flag_unsupported_claims("a lights to flag dominance")
    assert "got the jump" in flag_unsupported_claims("Russell got the jump at the start")
    assert "front-row" in flag_unsupported_claims("a front-row lockout for Ferrari")
    assert "sprint double" in flag_unsupported_claims("targeting a sprint double this weekend")
    assert "won both" in flag_unsupported_claims("McLaren won both the sprint and the race")


def test_flags_sprint_pole_leadership_regex():
    assert flag_unsupported_claims("He led from pole in the sprint before fading in the race")


def test_flags_retired_after_lap_number_regex():
    assert flag_unsupported_claims("Alonso retired after 37")


def test_flags_before_retiring_phrase():
    assert "before retiring" in flag_unsupported_claims("He lost ground before retiring from the race")
