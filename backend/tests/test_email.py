from datetime import datetime

from sqlmodel import select

from telogify import email as email_module
from telogify.email import (
    _choose_digest_design,
    _load_next_race,
    render_email,
    render_email_conversational,
    render_email_neubrutalist,
    render_email_plaintext,
    send_digest,
)
from telogify.models import Insight, QualiInsight, RaceWeekend


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


def _pace_spread():
    return {
        "fastest": "Mercedes",
        "rows": [("Ferrari", "+0.181s"), ("McLaren", "+0.940s"), ("Red Bull Racing", "+1.203s")],
    }


def _practice():
    return {
        "sectors": [
            (1, "Mercedes", "ANT", 0.019, 28.094),
            (2, "Mercedes", "ANT", 0.023, 35.623),
            (3, "McLaren", "NOR", 0.031, 24.512),
        ],
        "top_speed_driver": "HAM",
        "top_speed_constructor": "Ferrari",
        "top_speed_kmh": 322.0,
    }


def _quali_insight():
    return QualiInsight(
        weekend_id=1, slot=1, team="Mercedes",
        header="Mercedes’ qualifying edge showed up in the middle sector",
        explanation_web="web",
        explanation_email="Mercedes’ clearest qualifying edge over Ferrari was sector two, "
        "where the car was 0.093 seconds quicker. It held that edge into sector three too.",
        source_tool_calls_json=[],
    )


def test_render_email_has_three_insights_cta_and_no_table_without_pace_data():
    html = render_email(_weekend(), _insights(), "https://telogify.app")

    assert html.count("headline") == 3
    assert "Read the full analysis" in html
    assert "https://telogify.app/weekends/2025/11" in html
    # only the outer Outlook-centering shell -- the pace-spread panel self-hides when there's
    # no real per-constructor data to show (never falls back to placeholder content)
    assert html.count("<table") == 1
    assert "Pace spread" not in html


def test_render_email_cta_button_is_full_width_and_concise():
    html = render_email(_weekend(), _insights(), "https://telogify.app")
    assert 'display:block;box-sizing:border-box;width:100%' in html
    assert "Read the full analysis.</a>" in html
    # not the old, wordier label
    assert "Read the full analysis on the site." not in html


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


def test_render_email_opener_notes_when_winner_did_not_have_the_fastest_pace():
    html = render_email(
        _weekend(), _insights(), "https://telogify.app",
        winner=_winner(), pace_spread=_pace_spread(),
    )
    assert (
        "Charles Leclerc won for Ferrari this weekend, even though Mercedes had the "
        "faster race pace. Here’s what the telemetry found." in html
    )


def test_render_email_opener_notes_when_winner_also_had_the_fastest_pace():
    pace_spread = {"fastest": "Ferrari", "rows": _pace_spread()["rows"]}
    html = render_email(
        _weekend(), _insights(), "https://telogify.app",
        winner=_winner(), pace_spread=pace_spread,
    )
    assert (
        "Charles Leclerc won for Ferrari this weekend, the fastest car on pace too. "
        "Here’s what the telemetry found." in html
    )


def test_render_email_opener_uses_pace_spread_alone_without_a_winner():
    html = render_email(
        _weekend(), _insights(), "https://telogify.app", pace_spread=_pace_spread()
    )
    assert "Here’s what the telemetry found this weekend, with Mercedes setting the pace." in html


def test_render_email_pace_spread_panel_uses_real_data():
    html = render_email(
        _weekend(), _insights(), "https://telogify.app", pace_spread=_pace_spread()
    )
    assert "Pace spread &middot; Constructors" in html
    # the fastest team's name drives the sentence, not a hardcoded "Mercedes"
    assert "Mercedes set the pace this weekend." in html
    for name in ("Ferrari", "McLaren", "Red Bull Racing"):
        assert name in html
    for gap in ("+0.181s", "+0.940s", "+1.203s"):
        assert gap in html
    assert "placeholder" not in html.lower()


def test_render_email_teases_the_full_site_analysis():
    html = render_email(_weekend(), _insights(), "https://telogify.app")
    assert "fraction of what’s in the full weekend analysis" in html
    assert "tyre degradation by compound" in html


def test_render_email_has_sign_off_before_copyright():
    html = render_email(_weekend(), _insights(), "https://telogify.app")
    assert "See you after the next session." in html
    # sign-off comes before the legal line, not after
    assert html.index("See you after the next session.") < html.index("Tanish Misra")


def test_render_email_card_body_is_a_single_sentence():
    # names here don't matter for the pace-spread panel since it's omitted by default
    # (pace_spread=None) in this test -- "not in html" just checks truncation worked
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
    next_race = {
        "round": 10, "name": "Belgian Grand Prix", "place": "Spa, Belgium", "days": 6,
        "length_km": 7.004,
    }
    html = render_email(
        _weekend(), _insights(), "https://telogify.app", next_race=next_race
    )
    assert "Mirco Bartolozzi" in html
    assert 'href="https://telogify.app/unsubscribe"' in html
    assert "Next race &middot; Round 10" in html
    assert ">Belgian Grand Prix<" in html
    assert "Spa, Belgium" in html
    assert ">6<" in html and "days away" in html
    assert ">7.004<" in html and "km circuit" in html

    html_without = render_email(_weekend(), _insights(), "https://telogify.app")
    assert "Next race &middot;" not in html_without


def test_render_email_next_race_today_and_tomorrow_use_words_not_numbers():
    for days, word in ((0, "Today"), (1, "Tomorrow")):
        next_race = {"round": 10, "name": "Belgian Grand Prix", "place": "", "days": days}
        html = render_email(
            _weekend(), _insights(), "https://telogify.app", next_race=next_race
        )
        assert f">{word}<" in html
        assert "days away" not in html  # "Today"/"Tomorrow" carry no separate caption


def test_render_email_next_race_omits_circuit_length_when_unknown():
    next_race = {"round": 10, "name": "Made Up Grand Prix", "place": "", "days": 6}
    html = render_email(
        _weekend(), _insights(), "https://telogify.app", next_race=next_race
    )
    assert "km circuit" not in html


def test_render_email_pace_spread_gap_uses_darkened_team_color():
    html = render_email(
        _weekend(), _insights(), "https://telogify.app", pace_spread=_pace_spread()
    )
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
        pace_spread=_pace_spread(),
    )
    assert "<" not in text and ">" not in text
    assert (
        "Charles Leclerc won for Ferrari this weekend, even though Mercedes had the "
        "faster race pace." in text
    )
    assert "Insight 1 headline" in text
    assert "https://telogify.app/weekends/2025/11" in text
    assert "Mercedes set the pace this weekend." in text
    assert "Ferrari: +0.181s" in text
    assert "NEXT RACE - ROUND 10" in text
    assert "Belgian Grand Prix (Spa, Belgium), in 6 days" in text
    assert "Unsubscribe: https://telogify.app/unsubscribe" in text
    assert "—" not in text


def test_render_email_plaintext_omits_next_race_when_absent():
    text = render_email_plaintext(_weekend(), _insights(), "https://telogify.app")
    assert "NEXT RACE" not in text


def test_render_email_plaintext_omits_pace_spread_when_absent():
    text = render_email_plaintext(_weekend(), _insights(), "https://telogify.app")
    assert "PACE SPREAD" not in text


def test_render_email_practice_section_shows_sector_dominance_and_top_speed():
    html = render_email(
        _weekend(), _insights(), "https://telogify.app", practice=_practice()
    )
    assert "Fast out the gates" in html
    # each sector gets a bold, fixed-width S1/S2/S3/TS label as the primary anchor, so the
    # three sector rows read as distinct at a glance instead of resembling one another
    assert ">S1<" in html and ">S2<" in html and ">S3<" in html and ">TS<" in html
    # constructor + driver anchor the left side; the figure that matters is right-aligned and
    # bold, mirroring the pace-spread panel's identity-left/figure-right split
    assert ">Mercedes<" in html and ">McLaren<" in html and ">Ferrari<" in html
    assert ">Kimi Antonelli<" in html and ">Lando Norris<" in html and ">Lewis Hamilton<" in html
    assert ">0.019s<" in html and ">0.031s<" in html
    assert "clear" in html
    # driver full name, not the FastF1 code, and both units per the dual-unit citation rule
    assert ">322 km/h<" in html and "200 mph" in html

    html_without = render_email(_weekend(), _insights(), "https://telogify.app")
    assert "Fast out the gates" not in html_without


def test_render_email_qualifying_section_shows_one_quali_insight():
    html = render_email(
        _weekend(), _insights(), "https://telogify.app", quali_insight=_quali_insight()
    )
    assert "Setting the grid" in html
    assert "Mercedes’ qualifying edge showed up in the middle sector" in html
    # only the first sentence, same truncation rule as the race insight cards; "0.093 seconds"
    # is wrapped in its own <span> by number-emphasis, so check the two halves separately
    assert "0.093 seconds" in html
    assert "quicker." in html
    assert "It held that edge into sector three too" not in html
    assert ">Mercedes<" in html  # the team-color label row

    html_without = render_email(_weekend(), _insights(), "https://telogify.app")
    assert "Setting the grid" not in html_without


def test_render_email_next_race_is_a_real_panel_again():
    next_race = {
        "round": 10, "name": "Belgian Grand Prix", "place": "Spa, Belgium", "days": 6,
        "length_km": 7.004,
    }
    html = render_email(
        _weekend(), _insights(), "https://telogify.app", next_race=next_race
    )
    # earns a real bordered/shadowed panel again, same shell as the other panels, now that it
    # carries a heading, location, and two stats instead of one lonely countdown number
    assert "box-shadow:4px 4px 0 #1b1612" in html
    assert "Next race &middot; Round 10" in html
    assert ">Belgian Grand Prix<" in html
    assert "Belgian Grand Prix" in html


def test_render_email_plaintext_has_practice_and_qualifying_sections():
    text = render_email_plaintext(
        _weekend(), _insights(), "https://telogify.app",
        practice=_practice(), quali_insight=_quali_insight(),
    )
    assert "FAST OUT THE GATES" in text
    assert "S1: Mercedes (Kimi Antonelli), 0.019s clear" in text
    assert "TS: Ferrari (Lewis Hamilton), 322 km/h (200 mph)" in text
    assert "SETTING THE GRID" in text
    assert "Mercedes’ qualifying edge showed up in the middle sector" in text


def test_render_email_insight_cards_use_team_color_border():
    insights = [
        Insight(
            weekend_id=1, slot=1, team="Ferrari", header="Insight 1 headline",
            explanation_web="web", explanation_email="Ferrari were fast.",
            source_tool_calls_json=[],
        )
    ]
    html = render_email(_weekend(), insights, "https://telogify.app")
    assert "border:1.5px solid #E8002D" in html


def test_render_email_insight_card_falls_back_to_ink_border_without_team():
    html = render_email(_weekend(), _insights(), "https://telogify.app")  # _insights() sets no team
    assert "border:1.5px solid #1b1612" in html


def test_load_next_race_place_is_city_only(monkeypatch):
    from telogify.analysis.schedule import Event

    fake_event = Event(
        round=12, name="Belgian Grand Prix", date=datetime(2099, 1, 1),
        country="Belgium", location="Spa",
    )
    monkeypatch.setattr(email_module, "fetch_season_schedule", lambda year: (fake_event,))
    next_race = _load_next_race(now=datetime(2098, 12, 1))
    assert next_race["place"] == "Spa"
    assert "Belgium" not in next_race["place"]


def test_render_email_neubrutalist_renders_core_content():
    next_race = {
        "round": 10, "name": "Belgian Grand Prix", "place": "Spa", "days": 6, "length_km": 7.004,
    }
    html = render_email_neubrutalist(
        _weekend(), _insights(), "https://telogify.app",
        winner=_winner(), pace_spread=_pace_spread(), practice=_practice(),
        quali_insight=_quali_insight(), next_race=next_race,
    )
    # full standalone document (real webfonts need a <head>), mirroring digest-v59.html
    assert html.lower().startswith("<!doctype html>")
    assert "<style>" in html
    assert "fonts.googleapis.com" in html and "Archivo+Black" in html and "Space+Mono" in html
    assert "READ THE FULL ANALYSIS" in html
    assert "Belgian Grand Prix" in html
    # practice headlines the real absolute sector time (28.094s), not the margin (0.019s)
    assert "28.094s" in html
    assert "0.019s" not in html
    assert "#E8002D" in html  # Ferrari team color present (top speed row)
    # ransom-note headline: first name plain, surname big/red, verdict in a black box, rival
    # team wavy-underlined
    assert '<span class="a">Charles</span>' in html
    # surname is styled in the winner's team color, not a fixed hex
    assert '<span class="b" style="color:#E8002D">LECLERC</span>' in html
    assert '<span class="c">WON</span>' in html
    assert '<span class="e">Mercedes</span>' in html
    # next-race panel is light (matching v59), not the dark-inverted regression
    assert '<div class="next-race">' in html


def test_render_email_conversational_renders_core_content():
    next_race = {
        "round": 10, "name": "Belgian Grand Prix", "place": "Spa", "days": 6, "length_km": 7.004,
    }
    html = render_email_conversational(
        _weekend(), _insights(), "https://telogify.app",
        winner=_winner(), pace_spread=_pace_spread(), practice=_practice(),
        quali_insight=_quali_insight(), next_race=next_race,
        now=datetime(2026, 7, 20, 15, 0),  # a Monday
    )
    # full standalone document (real webfonts need a <head>), mirroring digest-v64.html
    assert html.lower().startswith("<!doctype html>")
    assert "<style>" in html
    assert "fonts.googleapis.com" in html and "Instrument+Sans" in html and "JetBrains+Mono" in html
    assert "Belgian Grand Prix" in html
    assert "7.004 km circuit" in html
    assert "MONDAY" in html
    assert "6:42" not in html and ":00<" not in html  # day only, no time-of-day
    # insight text is verbatim, not paraphrased
    assert "Insight 1 headline" in html
    # practice shows the real absolute sector time, not the margin
    assert "28.094s" in html
    assert "0.019s" not in html
    # typing indicator (static dots -- email clients don't animate reliably)
    assert 'class="typing"' in html and "Telogify is typing" in html
    # v64's real two-part CTA: a decorative non-clickable "sent" bubble, plus a separate real link
    assert '<div class="sent-bubble">I want to read the full analysis!</div>' in html
    assert '<a class="qr" href="https://telogify.app/weekends/2025/11">Read the full analysis' in html
    # numbers inside insight/qualifying prose get the .num highlight treatment (v64), unlike
    # Neubrutalist's plain body text
    assert '<span class="num">12 km/h</span>' in html


def test_render_digest_preview_uses_override_then_stored_then_production_default(db_session):
    wk = RaceWeekend(year=2026, round=9, circuit_name="Silverstone", country="UK", event_name="British Grand Prix")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    db_session.add(Insight(
        weekend_id=wk.id, slot=1, header="H1", explanation_web="w",
        explanation_email="E1.", source_tool_calls_json=[],
    ))
    db_session.commit()

    # no design set yet, no override -> falls back to production
    from telogify.email import render_digest_preview
    html = render_digest_preview(2026, 9, db_session)
    assert "telogify.app" not in html  # sanity: base_url comes from settings, not hardcoded
    assert "<style" not in html  # production's own convention holds

    # explicit override wins regardless of what's stored
    html = render_digest_preview(2026, 9, db_session, design="neubrutalist")
    assert "READ THE FULL ANALYSIS" in html

    # never persists anything -- repeated previews don't touch digest_design
    db_session.refresh(wk)
    assert wk.digest_design is None

    # once a design is actually stored, preview reuses it without an override
    wk.digest_design = "conversational"
    db_session.add(wk)
    db_session.commit()
    html = render_digest_preview(2026, 9, db_session)
    assert "Read the full analysis" in html


def test_choose_digest_design_first_send_is_production():
    assert _choose_digest_design([]) == "production"


def test_choose_digest_design_never_repeats_and_cycles_through_all_three():
    history: list[str] = []
    for _ in range(30):
        design = _choose_digest_design(history)
        if history:
            assert design != history[-1]
        history.append(design)
    assert history[0] == "production"
    for i in range(0, len(history) - 2, 3):
        assert set(history[i:i + 3]) == {"production", "neubrutalist", "conversational"}


def test_send_digest_raises_without_api_key(db_session, monkeypatch):
    monkeypatch.setattr(email_module.settings, "resend_api_key", None)
    try:
        send_digest(2026, 9, db_session)
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "RESEND_API_KEY" in str(e)


def test_send_digest_returns_zero_with_no_subscribers(db_session, monkeypatch):
    monkeypatch.setattr(email_module.settings, "resend_api_key", "fake-key")
    wk = RaceWeekend(year=2026, round=9, circuit_name="Silverstone", country="UK", event_name="British Grand Prix")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    db_session.add(Insight(
        weekend_id=wk.id, slot=1, header="H1", explanation_web="w",
        explanation_email="E1.", source_tool_calls_json=[],
    ))
    db_session.commit()
    assert send_digest(2026, 9, db_session) == 0  # no recipients arg, no Subscriber rows in DB


def test_send_digest_persists_chosen_design_and_reuses_on_resend(db_session, monkeypatch):
    monkeypatch.setattr(email_module.settings, "resend_api_key", "fake-key")
    monkeypatch.setattr(email_module.settings, "resend_from", "digest@telogify.app")
    sent = []
    monkeypatch.setattr(
        "resend.Emails.send", lambda params: sent.append(params) or {"id": "fake"}
    )

    wk = RaceWeekend(year=2026, round=9, circuit_name="Silverstone", country="UK", event_name="British Grand Prix")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    for i in range(1, 4):
        db_session.add(Insight(
            weekend_id=wk.id, slot=i, header=f"H{i}", explanation_web="w",
            explanation_email=f"E{i}.", source_tool_calls_json=[],
        ))
    db_session.commit()

    count = send_digest(2026, 9, db_session, recipients=["a@example.com"])
    assert count == 1
    assert len(sent) == 1

    db_session.refresh(wk)
    assert wk.digest_design in ("production", "neubrutalist", "conversational")
    chosen = wk.digest_design

    # a second send for the same weekend reuses the design instead of re-rolling
    send_digest(2026, 9, db_session, recipients=["b@example.com"])
    db_session.refresh(wk)
    assert wk.digest_design == chosen
