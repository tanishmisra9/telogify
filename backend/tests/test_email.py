from datetime import datetime

from telogify import email as email_module
from telogify.email import (
    _load_next_race,
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
    # attempt 5: Space Mono dropped -- body prose moved to a plain sans (never rendered in
    # Gmail anyway; the design's character lives in the bold display headers, not mono)
    assert "fonts.googleapis.com" in html and "Archivo+Black" in html
    assert "Space+Mono" not in html
    assert "READ THE FULL ANALYSIS" in html
    assert "Belgian Grand Prix" in html
    # practice headlines the real absolute sector time (28.094s), not the margin (0.019s)
    assert "28.094s" in html
    assert "0.019s" not in html
    assert "#E8002D" in html  # Ferrari team color present (top speed row)
    # attempt 6: one-line headline, uniform size -- driver name in the winner's team color,
    # verdict in a black box, no more mixed-size ransom-note spans
    assert '<span class="name" style="color:#E8002D">CHARLES LECLERC</span>' in html
    assert '<span class="verdict">WON FOR FERRARI!</span>' in html
    # sub-line names the faster rival when it differs from the winner's own team
    assert "Though Mercedes had the faster race pace." in html
    assert "Here&rsquo;s what actually happened!" in html
    assert ", sector by sector" not in html
    # attempt 7 item 2: WINNER stamp is always black/white now (was team-colored, forcing a
    # per-team ink/white contrast pick). attempt 8: the verdict's highlight box read as loud/bad
    # on real sends, so it's plain brand-red text now, no background.
    assert '>WINNER</' in html
    assert 'background:#0a0a0a' in html and 'color:#fff' in html
    assert '.headline .verdict { color: #0a0a0a; }' in html
    # attempt 7 item 1: capital T in the wordmark, matching the site's own casing
    assert '<p class="wordmark" style="margin:0;">Telo<span>gify</span></p>' in html
    # masthead icon: one hosted flat PNG baking in the whole shadow-box look (immune to Gmail's
    # dark-mode inversion, unlike the live white-bg/black-border box it replaced).
    assert '<img src="https://telogify.app/logo-chip.png"' in html
    # attempt 7 item 3: pace-gap figure is plain ink now, not a per-team darkened variant that
    # drifted away from the swatch's true color
    assert f'font-size:28px;color:#0a0a0a;">+0.181s' in html
    # next-race panel is light (matching v59), not the dark-inverted regression
    assert 'class="next-race-inner"' in html
    # attempt 5: off-white #FEFEFE not pure #fff (dark-mode best effort -- Gmail's auto-invert
    # is measurably less aggressive on near-white than pure white)
    assert 'background:#FEFEFE' in html
    # attempt 6 copy fixes
    assert "SUNDAY&rsquo;S FRONT RUNNERS" in html
    assert "YOUR 3 INSIGHTS" in html
    assert "FAST OUT THE GATES IN PRACTICE" in html
    # next-race stat label sits inline right of the number (item 7), not display:block below it
    assert '<span class="stat-label">days away</span>' in html
    assert '<span class="stat-label">km circuit</span>' in html
    # top speed mph moves onto the value line, not appended to the driver's name (item 10)
    assert "322 km/h" in html and "(200 mph)" in html
    assert "Lewis Hamilton (200 mph)" not in html


def test_render_digest_preview_renders_neubrutalist(db_session):
    wk = RaceWeekend(year=2026, round=9, circuit_name="Silverstone", country="UK", event_name="British Grand Prix")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    db_session.add(Insight(
        weekend_id=wk.id, slot=1, header="H1", explanation_web="w",
        explanation_email="E1.", source_tool_calls_json=[],
    ))
    db_session.commit()

    from telogify.email import render_digest_preview
    html = render_digest_preview(2026, 9, db_session)
    assert html.lower().startswith("<!doctype html>")
    assert "READ THE FULL ANALYSIS" in html


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


def test_send_digest_sends_neubrutalist_to_each_recipient(db_session, monkeypatch):
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

    count = send_digest(2026, 9, db_session, recipients=["a@example.com", "b@example.com"])
    assert count == 2
    assert len(sent) == 2
    assert all("READ THE FULL ANALYSIS" in params["html"] for params in sent)
