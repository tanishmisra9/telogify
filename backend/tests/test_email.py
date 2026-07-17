from telogify.email import render_email, render_email_plaintext
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


def _winner():
    return {"driver": "LEC", "constructor": "Ferrari"}


def test_render_email_has_three_insights_cta_and_pace_spread_table():
    html = render_email(_weekend(), _insights(), "https://telogify.app")

    assert html.count("headline") == 3
    assert "Read the full analysis" in html
    assert "https://telogify.app/weekends/2025/11" in html
    # outer Outlook-centering shell + the constructors pace-spread panel's row table (always
    # rendered, static placeholder content, not gated on any data)
    assert html.count("<table") == 2


def test_render_email_emphasizes_every_number():
    insights = [
        Insight(
            weekend_id=1, slot=1, header="Insight 1 headline", explanation_web="web",
            explanation_email="Ferrari were 12 km/h down through corner 4 for 2 laps.",
            source_tool_calls_json=[],
        )
    ]
    html = render_email(_weekend(), insights, "https://telogify.app")
    # the slot label ("01") also uses the mono font, so match the number-span tag specifically
    assert html.count('<span style="font-family:ui-monospace') == 3
    assert "12 km/h" in html
    assert ">4<" in html
    assert ">2<" in html


def test_render_email_does_not_emphasize_digits_in_name_tokens():
    insights = [
        Insight(
            weekend_id=1, slot=1, header="Insight 1 headline", explanation_web="web",
            explanation_email="Haas F1 Team gained 0.3 seconds through corner 4.",
            source_tool_calls_json=[],
        )
    ]
    html = render_email(_weekend(), insights, "https://telogify.app")
    # only "0.3 seconds" and "4" are data; the 1 in "F1" is part of the team name
    assert html.count('<span style="font-family:ui-monospace') == 2
    assert "0.3 seconds" in html
    assert "Haas F1 Team" in html


def test_render_email_has_wordmark_and_preheader():
    html = render_email(_weekend(), _insights(), "https://telogify.app")
    assert "Telo" in html and "gify" in html
    assert "display:none" in html


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


def test_render_email_opener_names_the_winner():
    html = render_email(_weekend(), _insights(), "https://telogify.app", winner=_winner())
    # generic about the weekend (no event name) -- the kicker above it already names it
    assert "Charles Leclerc won for Ferrari this weekend." in html
    # the opener seeds the preheader, not the first insight's header
    assert html.count("Charles Leclerc won for Ferrari this weekend.") == 2


def test_render_email_opener_falls_back_without_winner():
    html = render_email(_weekend(), _insights(), "https://telogify.app")
    assert "Here’s what the telemetry found this weekend." in html


def test_render_email_pace_spread_placeholder_panel():
    html = render_email(_weekend(), _insights(), "https://telogify.app")
    assert "Pace spread &middot; Constructors" in html
    assert "Pace spread &middot; Drivers" not in html
    assert "Illustrative placeholder numbers for layout review, not real data." in html
    for name in ("Ferrari", "McLaren", "Red Bull Racing"):
        assert name in html
    for gap in ("+0.181s", "+0.940s", "+1.203s"):
        assert gap in html


def test_render_email_teases_the_full_site_analysis():
    html = render_email(_weekend(), _insights(), "https://telogify.app")
    assert "fraction of what’s in the full weekend analysis" in html
    assert "tyre degradation by compound" in html


def test_render_email_card_body_is_a_single_sentence():
    # names here deliberately avoid the pace-spread placeholder panel's hardcoded roster
    # (Ferrari/McLaren/Red Bull Racing), so "not in html" is a clean check
    insights = [
        Insight(
            weekend_id=1, slot=1, header="H", explanation_web="w",
            explanation_email="Aston Martin ranked second on pace, 0.181 seconds off Williams. "
            "Williams was quickest overall and Oscar Piastri finished second.",
            source_tool_calls_json=[],
        )
    ]
    html = render_email(_weekend(), insights, "https://telogify.app")
    # "0.181 seconds" is wrapped in its own <span>, so check the two halves separately
    assert "0.181 seconds" in html
    assert "off Williams." in html
    assert "Oscar Piastri" not in html


def test_render_email_footer_has_credit_unsubscribe_and_next_race():
    next_race = {"round": 10, "name": "Belgian Grand Prix", "place": "Spa, Belgium", "days": 6}
    html = render_email(
        _weekend(), _insights(), "https://telogify.app", next_race=next_race
    )
    assert "Mirco Bartolozzi" in html
    assert 'href="https://telogify.app/unsubscribe"' in html
    assert "Next race &middot; Round 10" in html
    # a standalone oversized red-mono figure, not a number buried mid-sentence
    assert '<span style="font-family:ui-monospace' in html and ">6</span>" in html
    assert ">days</span>" in html
    assert "Belgian Grand Prix &middot; Spa, Belgium" in html

    html_without = render_email(_weekend(), _insights(), "https://telogify.app")
    assert "Next race &middot;" not in html_without


def test_render_email_next_race_today_and_tomorrow_use_words_not_numbers():
    for days, word in ((0, "Today"), (1, "Tomorrow")):
        next_race = {"round": 10, "name": "Belgian Grand Prix", "place": "", "days": days}
        html = render_email(
            _weekend(), _insights(), "https://telogify.app", next_race=next_race
        )
        assert f">{word}</span>" in html


def test_render_email_pace_spread_gap_uses_darkened_team_color():
    html = render_email(_weekend(), _insights(), "https://telogify.app")
    # each row's gap number picks up a darkened shade of ITS OWN team color, not the fixed
    # brand accent -- so a red Ferrari number and an orange McLaren number don't both fight
    # the exact same red as their differently-colored row tints
    assert "color:#8b001b\">+0.181s" in html  # Ferrari, darkened from #E8002D
    assert "color:#994c00\">+0.940s" in html  # McLaren, darkened from #FF8000
    assert "color:#204376\">+1.203s" in html  # Red Bull Racing, darkened from #3671C6
    assert f'font-weight:600;color:{"#E10600"}">+0.181s' not in html


def test_render_email_plaintext_has_core_content_no_html():
    text = render_email_plaintext(
        _weekend(), _insights(), "https://telogify.app", winner=_winner(),
        next_race={"round": 10, "name": "Belgian Grand Prix", "place": "Spa, Belgium", "days": 6},
    )
    assert "<" not in text and ">" not in text
    assert "Charles Leclerc won for Ferrari this weekend." in text
    assert "Insight 1 headline" in text
    assert "https://telogify.app/weekends/2025/11" in text
    assert "Ferrari: +0.181s" in text
    assert "NEXT RACE - ROUND 10" in text
    assert "Belgian Grand Prix (Spa, Belgium), in 6 days" in text
    assert "Unsubscribe: https://telogify.app/unsubscribe" in text
    assert "—" not in text


def test_render_email_plaintext_omits_next_race_when_absent():
    text = render_email_plaintext(_weekend(), _insights(), "https://telogify.app")
    assert "NEXT RACE" not in text
