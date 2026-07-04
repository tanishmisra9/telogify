from telogify.agent.guardrails import flag_unsupported_claims


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
