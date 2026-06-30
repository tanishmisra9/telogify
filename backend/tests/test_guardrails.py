from telogify.agent.guardrails import flag_unsupported_claims


def test_flags_the_audited_fabrications():
    # The exact failure phrases from the audit must be caught.
    assert flag_unsupported_claims("Antonelli's maiden Grand Prix win") == ["maiden"]
    assert "debut" in flag_unsupported_claims("Cadillac's debut weekend ends in retirement")
    assert "pole to flag" in flag_unsupported_claims("Antonelli led from pole to flag")
    assert "this season" in flag_unsupported_claims("his fourth win this season")


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
