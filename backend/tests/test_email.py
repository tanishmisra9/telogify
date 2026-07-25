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
    # ransom-note headline: first name plain, surname big/red, verdict in a black box, rival
    # team wavy-underlined
    assert '<span class="a">Charles</span>' in html
    # surname is styled in the winner's team color, not a fixed hex
    assert '<span class="b" style="color:#E8002D">LECLERC</span>' in html
    assert '<span class="c">WON</span>' in html
    assert '<span class="e">Mercedes</span>' in html
    # next-race panel is light (matching v59), not the dark-inverted regression
    assert 'class="next-race-inner"' in html
    # attempt 5: off-white #FEFEFE not pure #fff (dark-mode best effort -- Gmail's auto-invert
    # is measurably less aggressive on near-white than pure white)
    assert 'background:#FEFEFE' in html


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
