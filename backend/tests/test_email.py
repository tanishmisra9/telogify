import io
import re
from datetime import datetime
from urllib.parse import parse_qs, urlparse

from telogify import email as email_module
from telogify.chipgen import render_text_chip_png
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
    assert "%23E8002D" in html  # Ferrari team color present (top speed row, URL-encoded #E8002D)
    # attempt 6: one-line headline, uniform size -- driver name in the winner's team color,
    # verdict in a black box, no more mixed-size ransom-note spans.
    # Driver name is a dynamic chip image now (like the pace-spread swatches and WINNER above),
    # not live `color:` CSS -- a real send measured the bright team color (Mercedes teal) crushed
    # by Gmail's dark-mode inversion. font_size=29 (not .headline's 28px) matches Variant C's
    # own chip-drivername.png ink metrics -- see test_driver_name_chip_baseline_matches_live_text.
    assert (
        "chip/text.png?text=CHARLES+LECLERC&amp;font_size=29&amp;text_color=%23E8002D" in html
    )
    assert '<span class="verdict">WON FOR FERRARI!</span>' in html
    # sub-line names the faster rival when it differs from the winner's own team
    assert "Though Mercedes had the faster race pace." in html
    assert "Here&rsquo;s what actually happened!" in html
    assert ", sector by sector" not in html
    # attempt 7 item 2: WINNER stamp is always black/white now (was team-colored, forcing a
    # per-team ink/white contrast pick). attempt 8: the verdict's highlight box read as loud/bad
    # on real sends, so it's plain brand-red text now, no background.
    # WINNER is a hosted chip image now, not live CSS text -- immune to Gmail's dark-mode
    # rewriting, unlike the live black-bg/white-text box it replaced (real send measured that
    # box flipping to white-bg/black-text under Gmail's automatic inversion).
    assert '<img src="https://telogify.app/chips/chip-winner.png" width="138" height="52" alt="WINNER"' in html
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
    # attempt 6 copy fixes -- now hosted chip images too, same reasoning as WINNER above
    assert '<img src="https://telogify.app/chips/chip-section-pace.png"' in html
    assert 'alt="SUNDAY&rsquo;S FRONT RUNNERS"' in html
    assert '<img src="https://telogify.app/chips/chip-section-insights.png"' in html
    assert 'alt="YOUR 3 INSIGHTS"' in html
    assert '<img src="https://telogify.app/chips/chip-section-practice.png"' in html
    assert 'alt="FAST OUT THE GATES IN PRACTICE"' in html
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


def test_every_chip_image_can_shrink_to_fit_its_container():
    """A chip <img> carries a fixed pixel `width`, so without max-width it cannot shrink: too
    wide for its panel and it overflows, clipping the text and forcing the whole email to scroll
    sideways. Measured on a real render before this guard existed: the practice section title
    overflowed by 81px at a 390px viewport and the document scrolled horizontally at 320/390/430.

    Not a hypothetical -- ANDREA KIMI ANTONELLI renders a 354px driver-name chip against roughly
    251px of usable panel width on a 390px phone.
    """
    practice = {
        "sectors": [
            (1, "Mercedes", "ANT", 0.019, 28.094),
            (2, "Mercedes", "ANT", 0.023, 35.623),
            (3, "McLaren", "NOR", 0.031, 24.512),
        ],
        "top_speed_driver": "ANT", "top_speed_constructor": "Ferrari", "top_speed_kmh": 322.0,
    }
    html = render_email_neubrutalist(
        _weekend(), _insights(), "https://telogify.app",
        winner={"driver": "ANT", "constructor": "Mercedes"},
        pace_spread=_pace_spread(), practice=practice, quali_insight=_quali_insight(),
    )
    chips = re.findall(r'<img[^>]*?/chip(?:s|/text\.png)[^>]*>', html)
    assert chips, "expected chip images in the render"
    for chip in chips:
        assert "max-width:100%" in chip, f"chip cannot shrink, will overflow: {chip[:120]}"
        assert "height:auto" in chip, f"chip will squash when it shrinks: {chip[:120]}"


def test_sub_lead_is_plain_bold_with_no_highlight_and_no_forced_ink():
    """The lead line's yellow highlight is gone for good: #FFE500's luminance (~0.77) is far
    above the ~0.235 point where Gmail's dark-mode transform flips from lightening to crushing,
    so it rendered as a murky dark-olive bar.

    The second assertion is the real trap. The dark-mode block used to force `.sub b` to ink so
    it stayed legible ON the yellow. With the yellow gone that override would paint the lead
    near-black on a dark panel -- invisible. Restoring either rule alone is a bug, so both are
    pinned here together.
    """
    html = render_email_neubrutalist(
        _weekend(), _insights(), "https://telogify.app",
        winner=_winner(), pace_spread=_pace_spread(),
    )
    css = html.split("<style>")[1].split("</style>")[0]
    declarations = re.sub(r"/\*.*?\*/", "", css, flags=re.S)  # comments may mention the old hex
    assert "FFE500" not in declarations, "the yellow highlight is back"
    assert not re.search(r"\.sub b\s*\{", declarations), "a .sub b rule is back; see docstring"
    # emphasis still exists, carried by <b> alone
    assert "<b>Though Mercedes had the faster race pace.</b>" in html


def _chip_ink_metrics(png_bytes: bytes, scale: float = 3.0) -> dict:
    """Glyph (ink) height and the four ink-to-edge gaps, in display px. Distinct from the box
    size: a chip can match its target box exactly while the text inside still crowds the edges
    if the font is too big and the padding too small for that box -- exactly the bug this test
    exists to catch (see the docstring below)."""
    from PIL import Image

    im = png_bytes if isinstance(png_bytes, Image.Image) else Image.open(io.BytesIO(png_bytes))
    im = im.convert("RGBA")
    w, h = im.size
    px = im.load()
    bg = px[2, h // 2]  # a point inside the box but outside any glyph
    xs, ys = [], []
    for y in range(h):
        for x in range(w):
            p = px[x, y]
            hit = (
                p[3] > 60 if bg[3] < 40
                else p[3] > 60 and (abs(p[0]-bg[0])+abs(p[1]-bg[1])+abs(p[2]-bg[2])) > 120
            )
            if hit:
                xs.append(x)
                ys.append(y)
    assert xs, "no ink found in rendered chip"
    return {
        "cap": round((max(ys) - min(ys) + 1) / scale, 1),
        "top": round(min(ys) / scale, 1), "bot": round((h - 1 - max(ys)) / scale, 1),
        "left": round(min(xs) / scale, 1), "right": round((w - 1 - max(xs)) / scale, 1),
    }


# Ink metrics measured directly from Variant C's static PNGs (frontend/public/chips/*.png,
# deviceScaleFactor 3 -- still in the repo as ground truth). "cap" is glyph height; the rest are
# ink-to-edge gaps, i.e. the actual breathing room a viewer sees around the text.
_VC_INK_REFERENCE = {
    "SECTOR 1": dict(cap=11.3, top=6.0, bot=5.7, left=9.3, right=11.7),
    "TOP SPEED": dict(cap=11.3, top=6.0, bot=5.7, left=9.0, right=10.3),
    "QUALIFYING HOUR": dict(cap=13.3, top=7.0, bot=7.7, left=13.7, right=13.7),
    "01": dict(cap=13.7, top=9.7, bot=11.7, left=14.7, right=18.0),
    "Austrian Grand Prix": dict(cap=16.0, top=17.3, bot=18.7, left=24.7, right=25.7),
}


def test_dynamic_chip_ink_metrics_match_variant_c():
    """Pins each label chip's rendered TEXT (not just its box) to Variant C's measured ink
    metrics. A prior version of this test pinned box dimensions only, and that is exactly what
    let a real regression through: a font-size solved against box HEIGHT conflates size with
    padding, so a too-big font with too-little padding can hit the right box while the text still
    crowds the edges -- which is what "every png looks a bit smushed vertically" was. Confirmed
    this test fails with the box-matching-but-under-padded values it replaced (font 17/padding
    (4,10,4,10) for qualifying, e.g., left the bottom ink gap at 4.7px against Variant C's 7.7px).

    Tolerance is 1.5px, not 1px: SECTOR N and TOP SPEED share one padding value but end in
    different final glyphs ("1"/"2"/"3" vs "D"), so their own right-side kerning residue varies
    independently of anything this code controls -- confirmed by direct measurement, not assumed.
    """
    practice = {
        "sectors": [(1, "Mercedes", "RUS", 0.019, 27.726)],
        "top_speed_driver": "RUS", "top_speed_constructor": "Racing Bulls", "top_speed_kmh": 331.0,
    }
    html = render_email_neubrutalist(
        _weekend(), _insights(), "https://telogify.app",
        winner=_winner(), practice=practice, quali_insight=_quali_insight(),
    )

    for alt, target in _VC_INK_REFERENCE.items():
        m = re.search(rf'<img[^>]*alt="{re.escape(alt)}"[^>]*>', html)
        assert m, f"no chip found with alt={alt!r}"
        src = re.search(r'src="([^"]+)"', m.group()).group(1).replace("&amp;", "&")
        qs = {k: v[0] for k, v in parse_qs(urlparse(src).query).items()}
        png = render_text_chip_png(
            qs["text"], font_size=int(qs["font_size"]), text_color=qs["text_color"],
            bg_color=qs.get("bg_color"), letter_spacing_em=float(qs.get("letter_spacing_em", 0)),
            padding=(
                int(qs.get("padding_top", 0)), int(qs.get("padding_right", 0)),
                int(qs.get("padding_bottom", 0)), int(qs.get("padding_left", 0)),
            ),
        )
        got = _chip_ink_metrics(png)
        for metric, expected in target.items():
            actual = got[metric]
            assert abs(actual - expected) <= 1.5, (
                f"{alt!r} ink {metric}: got {actual}, Variant C is {expected} "
                f"(off by {abs(actual - expected)}px)"
            )


def test_driver_name_chip_baseline_matches_live_text():
    """The real acceptance criterion for driver-name alignment is not matching Variant C's own
    internal ink gaps (its ascent/descent split comes from real Arial Bold; this chip uses
    Liberation Sans Bold, a different font, so matching both the top AND bottom gap
    simultaneously via font-size alone is not achievable) -- it is whether the glyph's visible
    BOTTOM lines up with the live verdict text's baseline, which is the only thing a reader
    actually sees. vertical-align:-Npx shifts the image DOWN by N from the default (image bottom
    ON the baseline), so the ink sits `N - bot` px below the baseline -- comparing `bot` against
    Variant C's own 6.7px is the wrong check (a font-28 gap of 6.0 and a font-29 gap of 7.3 are
    each within 1px of 6.7, so that comparison can't tell them apart even though only one of them
    actually lands on the baseline). The right check is N == bot for THIS chip's own N and bot.

    Params are pulled from the actual rendered <img> src, not hand-typed -- a hardcoded
    font_size=29 here would keep "passing" even if _nb_headline_html's real font_size regressed,
    since it would just be re-measuring chipgen in isolation instead of what email.py produces.
    """
    html_out = render_email_neubrutalist(
        _weekend(), _insights(), "https://telogify.app", winner=_winner(),
    )
    m = re.search(r'<img[^>]*style="[^"]*vertical-align:-(\d+(?:\.\d+)?)px[^"]*"[^>]*>', html_out)
    assert m, "no driver-name chip found (vertical-align:-Npx marker)"
    align_px = float(m.group(1))
    src = re.search(r'src="([^"]+)"', m.group()).group(1).replace("&amp;", "&")
    qs = {k: v[0] for k, v in parse_qs(urlparse(src).query).items()}
    png = render_text_chip_png(
        qs["text"], font_size=int(qs["font_size"]), text_color=qs["text_color"],
    )
    got = _chip_ink_metrics(png)
    assert abs(align_px - got["bot"]) <= 0.5, (
        f"vertical-align is -{align_px}px but the chip's own bottom ink gap is {got['bot']}px -- "
        f"the glyph will sit {align_px - got['bot']:+.1f}px off the live text's baseline"
    )
