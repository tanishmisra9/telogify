from telogify.email import render_email
from telogify.models import Insight, RaceWeekend


def _weekend():
    return RaceWeekend(
        id=1, year=2025, round=11, circuit_name="Spielberg", country="Austria",
        event_name="Austrian Grand Prix",
    )


def _insights():
    return [
        Insight(
            weekend_id=1, slot=i,
            header=f"Insight {i} headline",
            explanation_web="web",
            explanation_email=f"Ferrari were 12 km/h down through the DRS zones in slot {i}.",
            source_tool_calls_json=[],
        )
        for i in range(1, 4)
    ]


def test_render_email_has_three_insights_cta_and_no_tables():
    html = render_email(_weekend(), _insights(), "https://telogify.app")

    assert html.count("headline") == 3
    assert "Read the full analysis" in html
    assert "https://telogify.app/weekends/2025/11" in html
    assert "<table" not in html  # the 3 insights are the email, no data dumps


def test_render_email_bolds_key_number():
    html = render_email(_weekend(), _insights()[:1], "https://telogify.app")
    assert "<strong" in html
    assert "12 km/h" in html


def test_render_email_strips_em_dashes():
    wk = _weekend()
    ins = [
        Insight(
            weekend_id=1, slot=1, header="Header — with dash", explanation_web="w",
            explanation_email="Body — with dash", source_tool_calls_json=[],
        )
    ]
    html = render_email(wk, ins, "https://telogify.app")
    assert "—" not in html
