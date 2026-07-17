"""Post-race email digest via Resend.

`render_email` is pure (testable): a big centered masthead, a one-line opener naming the
winner, "Here's your three insights" plus the 3 one-sentence insight cards, a placeholder
Constructors pace-spread panel (static layout-review content, not yet wired to real data), a
line teasing the full site analysis, a CTA, a next-race panel, and a footer with methodology
credit and copyright/unsubscribe. No em dashes. `render_email_plaintext` is its plain-text
sibling for the multipart/alternative text part. `send_digest` sends one message per subscriber
(both parts) so addresses are never shared across recipients.
"""

import html
import re
from datetime import datetime

from sqlmodel import Session
from sqlmodel import select

from telogify.analysis.schedule import fetch_season_schedule, pick_next_event
from telogify.analysis.sessions import pick_session
from telogify.config import settings
from telogify.models import Insight, RaceWeekend
from telogify.models import Session as SessionRow
from telogify.models import SessionResult, Subscriber
from telogify.serialize import strip_em_dashes

# Ported from frontend/src/lib/emphasize.tsx's NUM_RE: ordinals, then units with longer
# alternatives first (e.g. "seconds" before "s") so the shorter unit never wins early. The
# leading (?<![A-Za-z\d]) stops digits embedded in name tokens ("Haas F1 Team", "W17") reading
# as data; \d is included so a blocked run can't fall through to match its later digits.
_NUM_RE = re.compile(
    r"(?<![A-Za-z\d])\d[\d.,]*(?:st|nd|rd|th|\s?(?:seconds?|metres?|meters?|km/h|mph|m/s²|°C|%|km|m|s)(?![a-zA-Z]))?"
)
# A sentence boundary is punctuation followed by whitespace; a decimal point never has
# whitespace right after it (there's always another digit), so this never false-splits a number.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

# Same roster as agent/prompts.py's DRIVER NAMES block: the results table stores FastF1's
# 3-letter code, but the opener is prose voice and needs a full name. Unknown code -> print the
# code itself (never guess a name, matching the agent's own rule).
_DRIVER_NAMES = {
    "ALB": "Alexander Albon", "ALO": "Fernando Alonso", "ANT": "Kimi Antonelli",
    "BEA": "Oliver Bearman", "BOR": "Gabriel Bortoleto", "BOT": "Valtteri Bottas",
    "COL": "Franco Colapinto", "GAS": "Pierre Gasly", "HAD": "Isack Hadjar",
    "HAM": "Lewis Hamilton", "HUL": "Nico Hulkenberg", "LAW": "Liam Lawson",
    "LEC": "Charles Leclerc", "LIN": "Arvid Lindblad", "NOR": "Lando Norris",
    "OCO": "Esteban Ocon", "PER": "Sergio Perez", "PIA": "Oscar Piastri",
    "RUS": "George Russell", "SAI": "Carlos Sainz", "STR": "Lance Stroll",
    "VER": "Max Verstappen",
}


def _full_driver_name(code: str) -> str:
    return _DRIVER_NAMES.get(code, code)


_ACCENT = "#E10600"
_INK = "#1b1612"
_MUTED = "#605954"
_SURFACE = "#fffef0"
_ACCENT_INK = "#fdfaf3"
_HAIRLINE = "#ddd6c1"
_FONT_DISPLAY = "'Instrument Sans','Space Grotesk',system-ui,sans-serif"
_FONT_SANS = "'Space Grotesk',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif"
_FONT_MONO = "ui-monospace,'SF Mono','JetBrains Mono',Menlo,monospace"

# Ported from frontend/src/lib/teamColors.ts's TEAM_COLORS (2018+ naming variants).
_TEAM_COLORS = {
    "Red Bull Racing": "#3671C6", "Ferrari": "#E8002D", "Mercedes": "#27F4D2",
    "McLaren": "#FF8000", "Aston Martin": "#229971", "Alpine": "#0093CC",
    "Williams": "#64C4FF", "RB": "#6692FF", "AlphaTauri": "#6692FF",
    "Scuderia AlphaTauri": "#6692FF", "Kick Sauber": "#52E252", "Alfa Romeo": "#52E252",
    "Haas F1 Team": "#B6BABD", "Racing Bulls": "#6692FF", "Toro Rosso": "#469BFF",
    "Renault": "#FFF500", "Racing Point": "#F596C8", "Force India": "#F596C8",
    "Sauber": "#52E252", "Williams Racing": "#64C4FF", "Audi": "#F50537",
    "Cadillac": "#E8A33D",
}


def _team_color(team: str) -> str:
    return _TEAM_COLORS.get(team, _MUTED)


def _team_color_alpha(team: str, alpha: float) -> str:
    """Ported from teamColorWithAlpha in teamColors.ts, used at 0.09 for the site's row-wash
    pattern (Results.tsx, SeasonPage.tsx, QualiCharacterTable.tsx, DegradationChart.tsx)."""
    hex_color = _team_color(team)
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


def _darken(hex_color: str, factor: float = 0.6) -> str:
    """A row's gap number used to be fixed brand red regardless of team, which visibly clashed
    with a same-row tint in a different hue (e.g. red text on McLaren's orange wash). Darkening
    the row's own team color keeps the number legible and gives each row a coherent identity
    instead of two competing colors."""
    r = int(int(hex_color[1:3], 16) * factor)
    g = int(int(hex_color[3:5], 16) * factor)
    b = int(int(hex_color[5:7], 16) * factor)
    return f"#{r:02x}{g:02x}{b:02x}"


def _emphasize_numbers(escaped_text: str) -> str:
    return _NUM_RE.sub(
        lambda m: f'<span style="font-family:{_FONT_MONO};color:{_ACCENT}">{m.group(0)}</span>',
        escaped_text,
    )


def _clean(text: str) -> str:
    return html.escape(strip_em_dashes(text) or "")


def _first_sentence(text: str) -> str:
    """Safety net: the prompt asks the agent for exactly one sentence; this guarantees it
    even if a generation slips, without touching explanation_web."""
    parts = _SENTENCE_SPLIT_RE.split(text.strip())
    return parts[0] if parts else text


def _kicker(label: str, *, color: str = _MUTED, margin: str = "0 0 8px 0") -> str:
    return (
        f'<p style="margin:{margin};font-family:{_FONT_MONO};font-size:11px;'
        f'letter-spacing:0.15em;text-transform:uppercase;color:{color}">{label}</p>'
    )


def _opener_html(winner: dict | None) -> tuple[str, str]:
    """Returns (plain_text, html_paragraph) so the same sentence can seed the preheader.
    Stays generic about the weekend (no event name) since the kicker above it already
    names it."""
    if winner and winner["constructor"]:
        text = (
            f'{html.escape(_full_driver_name(winner["driver"]))} won for '
            f'{html.escape(winner["constructor"])} this weekend. Here’s what the telemetry found.'
        )
    else:
        text = "Here’s what the telemetry found this weekend."
    para = (
        f'<p style="margin:0 0 24px 0;font-family:{_FONT_SANS};font-size:15px;'
        f'line-height:1.6;color:{_INK}">{text}</p>'
    )
    return text, para


# ponytail: hardcoded layout-review placeholder, not wired to a real per-team pace gap yet --
# swap for a real query (constructor_median_gaps) once the panel design itself is signed off.
_PLACEHOLDER_CONSTRUCTOR_GAPS = [("Ferrari", "+0.181s"), ("McLaren", "+0.940s"), ("Red Bull Racing", "+1.203s")]


def _pace_spread_panel(kicker_suffix: str, sentence: str, rows: list[tuple[str, str]]) -> str:
    row_html = []
    for i, (name, gap) in enumerate(rows):
        border = "" if i == len(rows) - 1 else f"border-bottom:1px solid {_HAIRLINE};"
        # Row wash at the site's own alpha (Results.tsx/SeasonPage.tsx/etc. all use 0.09) plus
        # a TeamRule-style colored bar (frontend/src/components/TeamMark.tsx) -- color + text
        # only, no logos.
        wash = f"background-color:{_team_color_alpha(name, 0.09)};"
        rule = (
            f'<span style="display:inline-block;width:3px;height:15px;background:'
            f'{_team_color(name)};border-radius:2px;vertical-align:middle;margin-right:8px">'
            "</span>"
        )
        row_html.append(
            "<tr>"
            f'<td style="padding:12px 0 12px 10px;{border}{wash}font-family:{_FONT_SANS};'
            f'font-size:15px;color:{_INK}">{rule}{html.escape(name)}</td>'
            f'<td style="padding:12px 10px 12px 0;{border}{wash}text-align:right;'
            f'font-family:{_FONT_MONO};font-size:32px;font-weight:600;color:{_darken(_team_color(name))}">'
            f"{html.escape(gap)}</td>"
            "</tr>"
        )
    return (
        f'<div style="background:{_SURFACE};border:1.5px solid {_INK};box-shadow:4px 4px 0 {_INK};'
        f'border-radius:2px;padding:24px;margin:0 0 20px 0">'
        + _kicker(f"Pace spread &middot; {kicker_suffix}", color=_ACCENT)
        + f'<p style="margin:0 0 16px 0;font-family:{_FONT_SANS};font-size:14px;line-height:1.5;'
        f'color:{_INK}">{sentence}</p>'
        + f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border-top:1px solid {_HAIRLINE}">'
        + "".join(row_html)
        + "</table></div>"
    )


def _pace_spread_placeholder_html() -> str:
    disclaimer = (
        f'<p style="margin:0 0 16px 0;font-family:{_FONT_SANS};font-size:12px;color:{_MUTED}">'
        "Illustrative placeholder numbers for layout review, not real data.</p>"
    )
    return disclaimer + _pace_spread_panel(
        "Constructors",
        "Mercedes set the pace this weekend. Here’s how far back the next three fell, per lap.",
        _PLACEHOLDER_CONSTRUCTOR_GAPS,
    )


def _next_race_html(next_race: dict | None) -> str:
    """A compact version of the landing page's Countdown block: kicker, one oversized
    red-mono figure, then the race name/place as a caption -- not a sentence with the number
    buried mid-clause."""
    if next_race is None:
        return ""
    place = f" &middot; {html.escape(next_race['place'])}" if next_race.get("place") else ""
    days = next_race["days"]

    if days == 0:
        figure = f'<span style="font-family:{_FONT_DISPLAY};font-size:28px;font-weight:600;color:{_ACCENT}">Today</span>'
    elif days == 1:
        figure = f'<span style="font-family:{_FONT_DISPLAY};font-size:28px;font-weight:600;color:{_ACCENT}">Tomorrow</span>'
    else:
        figure = (
            f'<span style="font-family:{_FONT_MONO};font-size:40px;font-weight:600;'
            f'color:{_ACCENT};line-height:1;vertical-align:bottom">{days}</span>'
            f'<span style="font-family:{_FONT_MONO};font-size:12px;letter-spacing:0.1em;'
            f'text-transform:uppercase;color:{_MUTED};margin-left:8px;vertical-align:bottom;'
            'padding-bottom:6px;display:inline-block">days</span>'
        )

    return (
        f'<div style="background:{_SURFACE};border:1.5px solid {_INK};box-shadow:4px 4px 0 {_INK};'
        f'border-radius:2px;padding:16px 20px;margin:24px 0 0 0">'
        + _kicker(f"Next race &middot; Round {next_race['round']}", margin="0 0 6px 0")
        + f'<p style="margin:0">{figure}</p>'
        + f'<p style="margin:6px 0 0 0;font-family:{_FONT_SANS};font-size:12px;color:{_MUTED}">'
        f'{html.escape(next_race["name"])}{place}</p>'
        "</div>"
    )


def render_email(
    weekend: RaceWeekend,
    insights: list[Insight],
    base_url: str,
    *,
    winner: dict | None = None,
    next_race: dict | None = None,
) -> str:
    cta_url = f"{base_url.rstrip('/')}/weekends/{weekend.year}/{weekend.round}"
    event_name = html.escape(weekend.event_name)
    preheader_text, opener_html = _opener_html(winner)

    cards = []
    for i, ins in enumerate(insights, start=1):
        header = _clean(ins.header)
        body = _emphasize_numbers(_clean(_first_sentence(ins.explanation_email)))
        cards.append(
            f'<div style="background:{_SURFACE};border:1.5px solid {_INK};'
            f'box-shadow:4px 4px 0 {_INK};border-radius:2px;padding:24px;margin:0 0 20px 0">'
            f'<p style="margin:0 0 6px 0;font-family:{_FONT_MONO};font-size:12px;'
            f'letter-spacing:0.1em;color:{_ACCENT}">0{i}</p>'
            f'<h2 style="margin:0 0 8px 0;font-family:{_FONT_DISPLAY};font-size:18px;'
            f'font-weight:600;color:{_INK}">{header}</h2>'
            f'<p style="margin:0;font-size:15px;line-height:1.6;font-family:{_FONT_SANS};'
            f'color:{_INK}">{body}</p>'
            "</div>"
        )

    next_race_block = _next_race_html(next_race)
    methodology = (
        f'<p style="margin:24px 0 0 0;font-family:{_FONT_SANS};font-size:11px;line-height:1.6;'
        f'color:{_MUTED}">Methodology inputs come from Mirco Bartolozzi (@fdataanalysis), '
        "covering clean-air filtering, fuel correction, and the ERS depletion signal. "
        "Timing data comes from FastF1.</p>"
    )
    copyright_line = (
        f'<p style="margin:20px 0 0 0;font-family:{_FONT_SANS};font-size:11px;color:{_MUTED}">'
        f"&copy; {weekend.year} Tanish Misra &middot; "
        f'<a href="{html.escape(base_url.rstrip("/"))}/unsubscribe" style="color:{_MUTED};'
        'text-decoration:underline">Unsubscribe</a></p>'
    )

    return (
        f'<div style="display:none;max-height:0;overflow:hidden;opacity:0">{preheader_text}</div>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="background:#fffdd0"><tr><td align="center" style="padding:32px 16px">'
        '<div style="max-width:560px;margin:0 auto;text-align:left">'
        '<div style="margin:0 0 24px 0;text-align:center">'
        f'<span style="display:inline-block;border-bottom:2px solid {_ACCENT};padding-bottom:8px">'
        '<svg width="52" height="52" viewBox="0 0 32 32" fill="none" stroke-width="3" '
        'stroke-linecap="round" stroke-linejoin="round" '
        'style="display:inline-block;vertical-align:middle">'
        f'<path d="M2 16 L6 7 L10 25 L13 11 L16 20 L18 16" stroke="{_INK}"></path>'
        f'<path d="M18 16 L30 16" stroke="{_ACCENT}"></path>'
        "</svg>"
        f'<span style="display:inline-block;vertical-align:middle;margin-left:14px;'
        f'font-family:{_FONT_DISPLAY};font-size:72px;font-weight:400;color:{_INK}">Telo'
        f'<span style="color:{_ACCENT}">gify</span></span></span></div>'
        f'<p style="margin:0 0 28px 0;text-align:center;font-family:{_FONT_MONO};font-size:11px;'
        f'letter-spacing:0.22em;text-transform:uppercase;color:{_ACCENT}">{event_name}</p>'
        + opener_html
        + f'<p style="margin:44px 0 20px 0;font-family:{_FONT_DISPLAY};font-size:32px;'
        f'font-weight:600;letter-spacing:-0.02em;color:{_INK}">Here’s your three insights</p>'
        + "".join(cards)
        + _pace_spread_placeholder_html()
        + f'<p style="margin:0;font-family:{_FONT_SANS};font-size:15px;line-height:1.6;'
        f'color:{_INK}">This is a fraction of what’s in the full weekend analysis: tyre '
        "degradation by compound, sector dominance, qualifying car character, and the "
        "complete pace ranking.</p>"
        + f'<a href="{html.escape(cta_url)}" style="display:inline-block;margin-top:20px;'
        f"padding:12px 20px;background:{_ACCENT};color:{_ACCENT_INK};text-decoration:none;"
        f'border-radius:2px;font-family:{_FONT_SANS};font-size:14px;font-weight:600">'
        "Read the full analysis on the site.</a>"
        + next_race_block
        + methodology
        + copyright_line
        + "</div></td></tr></table>"
    )


def render_email_plaintext(
    weekend: RaceWeekend,
    insights: list[Insight],
    base_url: str,
    *,
    winner: dict | None = None,
    next_race: dict | None = None,
) -> str:
    """Plain-text sibling of render_email for the multipart/alternative text part sending
    infrastructure (and some spam filters) expect alongside the HTML. Real driver/team/circuit
    names never contain HTML-special characters, so reusing render_email's already-"escaped"
    opener text here is safe -- html.escape is a no-op on this domain's inputs."""
    cta_url = f"{base_url.rstrip('/')}/weekends/{weekend.year}/{weekend.round}"
    opener_text, _ = _opener_html(winner)

    lines = [f"TELOGIFY · {weekend.event_name}", "", opener_text, ""]

    lines.append("HERE'S YOUR THREE INSIGHTS")
    lines.append("")
    for i, ins in enumerate(insights, start=1):
        header = strip_em_dashes(ins.header) or ""
        body = strip_em_dashes(_first_sentence(ins.explanation_email)) or ""
        lines.append(f"{i:02d}. {header}")
        lines.append(body)
        lines.append("")

    lines.append("PACE SPREAD - CONSTRUCTORS")
    lines.append(
        "Mercedes set the pace this weekend. Here's how far back the next three fell, per lap."
    )
    for name, gap in _PLACEHOLDER_CONSTRUCTOR_GAPS:
        lines.append(f"  {name}: {gap}")
    lines.append("(Illustrative placeholder numbers for layout review, not real data.)")
    lines.append("")

    lines.append(
        "This is a fraction of what's in the full weekend analysis: tyre degradation by "
        "compound, sector dominance, qualifying car character, and the complete pace ranking."
    )
    lines.append("")
    lines.append(f"Read the full analysis: {cta_url}")
    lines.append("")

    if next_race is not None:
        place = f" ({next_race['place']})" if next_race.get("place") else ""
        days = next_race["days"]
        when = "today" if days == 0 else ("tomorrow" if days == 1 else f"in {days} days")
        lines.append(f"NEXT RACE - ROUND {next_race['round']}")
        lines.append(f"{next_race['name']}{place}, {when}")
        lines.append("")

    lines.append(
        "Methodology inputs come from Mirco Bartolozzi (@fdataanalysis), covering clean-air "
        "filtering, fuel correction, and the ERS depletion signal. Timing data comes from FastF1."
    )
    lines.append("")
    lines.append(f"© {weekend.year} Tanish Misra")
    lines.append(f"Unsubscribe: {base_url.rstrip('/')}/unsubscribe")

    return "\n".join(lines)


def _load_weekend_and_insights(
    year: int, round: int, db: Session
) -> tuple[RaceWeekend, list[Insight]]:
    weekend = db.exec(
        select(RaceWeekend).where(RaceWeekend.year == year, RaceWeekend.round == round)
    ).first()
    if weekend is None:
        raise RuntimeError(f"No weekend found for {year} round {round}.")

    insights = db.exec(
        select(Insight).where(Insight.weekend_id == weekend.id).order_by(Insight.slot)
    ).all()
    if not insights:
        raise RuntimeError("No insights to send. Run `telogify run-weekend` first.")

    return weekend, insights


def _load_winner(db: Session, weekend_id: int) -> dict | None:
    sessions = db.exec(select(SessionRow).where(SessionRow.weekend_id == weekend_id)).all()
    race = pick_session(sessions, ("R", "SPRINT"))
    if race is None:
        return None
    r = db.exec(
        select(SessionResult).where(
            SessionResult.session_id == race.id, SessionResult.position == 1
        )
    ).first()
    if r is None:
        return None
    return {"driver": r.driver, "constructor": r.constructor}


def _load_next_race(now: datetime | None = None) -> dict | None:
    """Mirrors the /next-race endpoint (analysis/schedule.py's pick_next_event), so the email's
    countdown cue and the landing page's countdown always agree."""
    now = now or datetime.utcnow()
    ev = pick_next_event(list(fetch_season_schedule(now.year)), now)
    if ev is None:
        ev = pick_next_event(list(fetch_season_schedule(now.year + 1)), now)
    if ev is None:
        return None
    days = max(0, (ev.date - now).days)
    place = ", ".join(p for p in (ev.location, ev.country) if p)
    return {"round": ev.round, "name": ev.name, "place": place, "days": days}


def _load_extras(db: Session, weekend: RaceWeekend) -> dict:
    return {
        "winner": _load_winner(db, weekend.id),
        "next_race": _load_next_race(),
    }


def render_digest_preview(year: int, round: int, db: Session) -> str:
    """Render the digest HTML for local preview. Never touches RESEND_API_KEY."""
    weekend, insights = _load_weekend_and_insights(year, round, db)
    return render_email(
        weekend, insights, settings.web_base_url, **_load_extras(db, weekend)
    )


def send_digest(year: int, round: int, db: Session, recipients: list[str] | None = None) -> int:
    """Send the digest to subscribers (or `recipients`). Returns the number sent."""
    if not settings.resend_api_key:
        raise RuntimeError("RESEND_API_KEY is not set; cannot send the digest.")

    weekend, insights = _load_weekend_and_insights(year, round, db)

    if recipients is None:
        recipients = [s.email for s in db.exec(select(Subscriber)).all()]
    if not recipients:
        return 0

    import resend

    resend.api_key = settings.resend_api_key
    extras = _load_extras(db, weekend)
    html_body = render_email(weekend, insights, settings.web_base_url, **extras)
    text_body = render_email_plaintext(weekend, insights, settings.web_base_url, **extras)
    subject = f"{weekend.event_name}: your 3 insights"

    for email in recipients:
        resend.Emails.send(
            {
                "from": settings.resend_from,
                "to": [email],
                "subject": subject,
                "html": html_body,
                "text": text_body,
            }
        )
    return len(recipients)
