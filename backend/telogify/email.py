"""Post-race email digest via Resend.

`render_email` is pure (testable): a big centered masthead, a one-line opener naming the
winner, a Practice section ("Fast out the gates": sector dominance + top speed), a Qualifying
section (one quali car-character insight), "Here's your three insights" plus the 3 race
insight cards, a Constructors pace-spread panel (real per-constructor race-pace gaps, the same
canonical median metric as the /pace chart and constructor ranking), a line teasing the full
site analysis, a CTA, a slim next-race line, and a footer with methodology credit and
copyright/unsubscribe. No em dashes. `render_email_plaintext` is its plain-text sibling for
the multipart/alternative text part. `send_digest` sends one message per subscriber (both
parts) so addresses are never shared across recipients.
"""

import html
import random
import re
from datetime import datetime

from sqlmodel import Session
from sqlmodel import select

from telogify.analysis.attribution import _driver_constructor_map
from telogify.analysis.constructor_index import _race_stints_as_dicts
from telogify.analysis.race_pace import constructor_median_gaps
from telogify.analysis.schedule import fetch_season_schedule, pick_next_event
from telogify.analysis.sectors import best_across_sessions, best_top_speeds, sector_dominance
from telogify.analysis.sessions import pick_session
from telogify.config import settings
from telogify.models import Insight, QualiInsight, RaceWeekend
from telogify.models import Session as SessionRow
from telogify.models import SectorBest, SessionResult, StraightSegment, Subscriber
from telogify.serialize import strip_em_dashes

# Same practice/sprint-quali session set the site's own /sectors and /topspeeds endpoints treat
# as "indicative" (api/routes.py's INDICATIVE_SESSIONS) -- conditions vary run to run, so these
# are read as a snapshot, not a qualifying-grade ranking.
_INDICATIVE_SESSIONS = ("FP1", "FP2", "FP3", "SQ")

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

# The shared insight-card/panel shell (cream surface, hard offset shadow, sharp corners) --
# every full-weight panel opens with this same div.
_PANEL_OPEN = (
    f'<div style="background:{_SURFACE};border:1.5px solid {_INK};box-shadow:4px 4px 0 {_INK};'
    'border-radius:2px;padding:24px;margin:0 0 20px 0">'
)

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

# Official FIA circuit lap lengths (km), keyed by event name -- a stable real-world fact, not
# something that needs a live lookup. Covers the modern-era calendar; an event name not found
# here just means the next-race panel skips the circuit-length stat, not an error.
_CIRCUIT_LENGTH_KM = {
    "Australian Grand Prix": 5.278, "Chinese Grand Prix": 5.451, "Japanese Grand Prix": 5.807,
    "Bahrain Grand Prix": 5.412, "Saudi Arabian Grand Prix": 6.174, "Miami Grand Prix": 5.412,
    "Emilia Romagna Grand Prix": 4.909, "Monaco Grand Prix": 3.337, "Canadian Grand Prix": 4.361,
    "Spanish Grand Prix": 4.657, "Austrian Grand Prix": 4.318, "British Grand Prix": 5.891,
    "Belgian Grand Prix": 7.004, "Hungarian Grand Prix": 4.381, "Dutch Grand Prix": 4.259,
    "Italian Grand Prix": 5.793, "Azerbaijan Grand Prix": 6.003, "Singapore Grand Prix": 4.940,
    "United States Grand Prix": 5.513, "Mexico City Grand Prix": 4.304,
    "São Paulo Grand Prix": 4.309, "Las Vegas Grand Prix": 6.201, "Qatar Grand Prix": 5.380,
    "Abu Dhabi Grand Prix": 5.281,
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
    # 12px + 0.1em tracking sits inside the eyebrow-label convention (12-14px, ~0.05em+ for
    # small-caps legibility) rather than our old 11px/0.15em, which ran both smaller and more
    # aggressively spaced than real digest labels tend to.
    return (
        f'<p style="margin:{margin};font-family:{_FONT_MONO};font-size:12px;'
        f'letter-spacing:0.1em;text-transform:uppercase;color:{color}">{label}</p>'
    )


def _opener_html(winner: dict | None, pace_spread: dict | None = None) -> tuple[str, str]:
    """Returns (plain_text, html_paragraph) so the same sentence can seed the preheader.
    Stays generic about the weekend (no event name) since the kicker above it already names
    it. Folds in the pace-spread panel's own fastest-team fact when available, so the opener
    carries a second real, already-computed detail instead of staying a bare one-liner --
    never a new claim, just an earlier mention of a fact the email states again below."""
    raw_team = winner["constructor"] if winner and winner["constructor"] else None
    raw_fastest = pace_spread["fastest"] if pace_spread else None
    driver = html.escape(_full_driver_name(winner["driver"])) if winner else None
    team = html.escape(raw_team) if raw_team else None
    fastest = html.escape(raw_fastest) if raw_fastest else None

    if driver and team and fastest:
        if raw_fastest == raw_team:
            text = (
                f"{driver} won for {team} this weekend, the fastest car on pace too. "
                "Here’s what the telemetry found."
            )
        else:
            text = (
                f"{driver} won for {team} this weekend, even though {fastest} had the "
                "faster race pace. Here’s what the telemetry found."
            )
    elif driver and team:
        text = f"{driver} won for {team} this weekend. Here’s what the telemetry found."
    elif fastest:
        text = f"Here’s what the telemetry found this weekend, with {fastest} setting the pace."
    else:
        text = "Here’s what the telemetry found this weekend."
    para = (
        f'<p style="margin:0 0 24px 0;font-family:{_FONT_SANS};font-size:15px;'
        f'line-height:1.6;color:{_INK}">{text}</p>'
    )
    return text, para


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
        _PANEL_OPEN
        + _kicker(f"Pace spread &middot; {kicker_suffix}")
        + f'<p style="margin:0 0 16px 0;font-family:{_FONT_SANS};font-size:15px;line-height:1.5;'
        f'color:{_INK}">{sentence}</p>'
        + f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border-top:1px solid {_HAIRLINE}">'
        + "".join(row_html)
        + "</table></div>"
    )


def _pace_spread_html(pace_spread: dict | None) -> str:
    if pace_spread is None:
        return ""
    fastest = html.escape(pace_spread["fastest"])
    sentence = (
        f"{fastest} set the pace this weekend. Here’s how far back the next three fell, per lap."
    )
    return _pace_spread_panel("Constructors", sentence, pace_spread["rows"])


def _next_race_html(next_race: dict | None) -> str:
    """A real panel again -- the slim single-line version traded boxed weight for cramming a
    kicker, a big number, a small unit label, and the full race name onto one baseline (three
    very different type scales on one line), which read as noise, not compact. This version
    earns the panel's weight back with real content instead: the race name as a heading, and
    two stats side by side (days away, circuit length) rather than one lonely countdown
    number -- so the panel has something to preview, not just a count."""
    if next_race is None:
        return ""
    days = next_race["days"]
    if days == 0:
        days_value, days_caption = "Today", ""
    elif days == 1:
        days_value, days_caption = "Tomorrow", ""
    else:
        days_value, days_caption = str(days), "days away"

    stats = [(days_value, days_caption)]
    length_km = next_race.get("length_km")
    if length_km is not None:
        stats.append((f"{length_km:.3f}", "km circuit"))

    # Matches the site's own CountdownPanel: number and unit sit in one baseline-aligned row
    # (flex items-baseline there; plain inline <span>s here default to the same baseline
    # alignment), the unit riding the number's floor to its right -- not stacked underneath.
    stat_cells = []
    for i, (value, caption) in enumerate(stats):
        align = "left"
        caption_html = (
            f'<span style="font-family:{_FONT_MONO};font-size:11px;letter-spacing:0.08em;'
            f'text-transform:uppercase;color:{_MUTED};margin-left:6px">{html.escape(caption)}</span>'
        ) if caption else ""
        stat_cells.append(
            f'<td style="width:{100 // len(stats)}%;text-align:{align};vertical-align:top">'
            f'<span style="font-family:{_FONT_MONO};font-size:28px;font-weight:600;'
            f'color:{_ACCENT}">{html.escape(value)}</span>{caption_html}</td>'
        )

    location = (
        f'<p style="margin:0 0 16px 0;font-family:{_FONT_SANS};font-size:13px;color:{_MUTED}">'
        f'{html.escape(next_race["place"])}</p>'
    ) if next_race.get("place") else ""

    # A bespoke panel-open (not the shared _PANEL_OPEN) with real top margin -- this panel sits
    # right after the CTA button, and _PANEL_OPEN's usual margin:0 0 20px 0 (no top margin) left
    # it flush against the button above with no breathing room.
    panel_open = (
        f'<div style="background:{_SURFACE};border:1.5px solid {_INK};box-shadow:4px 4px 0 {_INK};'
        'border-radius:2px;padding:24px;margin:32px 0 20px 0">'
    )
    return (
        panel_open
        + _kicker(f"Next race &middot; Round {next_race['round']}", margin="0 0 6px 0")
        + f'<h2 style="margin:0 0 4px 0;font-family:{_FONT_DISPLAY};font-size:19px;'
        f'letter-spacing:-0.01em;font-weight:600;color:{_INK}">{html.escape(next_race["name"])}</h2>'
        + location
        + '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
        + "".join(stat_cells)
        + "</tr></table></div>"
    )


def _section_heading(text: str) -> str:
    return (
        f'<p style="margin:44px 0 20px 0;font-family:{_FONT_DISPLAY};font-size:32px;'
        f'font-weight:600;letter-spacing:-0.02em;color:{_INK}">{text}</p>'
    )


def _practice_html(practice: dict | None) -> str:
    if practice is None:
        return ""
    # Each sector needs to read as a genuinely distinct row at a glance, not four lookalike
    # lines that differ only in small text. A bold, fixed-width S1/S2/S3/TS label anchors that
    # -- it's also what fixes alignment: a 2-character mono label never drifts, unlike
    # right-aligning variable-length constructor names ("McLaren" vs "Red Bull Racing") did.
    # Sector order is a real physical sequence (track position), so a numbered label is earned
    # here, not decorative scaffolding.
    #
    # The figure that actually matters now sits on the RIGHT, big and bold -- the exact same
    # identity-left/figure-right split the pace-spread panel already uses, so Practice reads as
    # the same visual language instead of its own one-off layout. Driver name is a smaller
    # caption under the constructor, gap/unit context a smaller caption under the figure.
    rows = []
    for sector, constructor, driver, margin, _best_time_s in practice["sectors"]:
        driver_name = _full_driver_name(driver) if driver else None
        value = f"{margin:.3f}s" if margin is not None else "—"
        rows.append((f"S{sector}", constructor, driver_name, value, "clear"))

    kmh = practice["top_speed_kmh"]
    mph = kmh * 0.621371
    top_constructor = practice["top_speed_constructor"]
    top_driver = _full_driver_name(practice["top_speed_driver"])
    rows.append(("TS", top_constructor, top_driver, f"{kmh:.0f} km/h", f"{mph:.0f} mph"))

    row_html = []
    for i, (label, constructor, driver_name, value, caption) in enumerate(rows):
        border = "" if i == len(rows) - 1 else f"border-bottom:1px solid {_HAIRLINE};"
        wash = f"background-color:{_team_color_alpha(constructor or '', 0.09)};"
        rule = (
            f'<span style="display:inline-block;width:3px;height:13px;background:'
            f'{_team_color(constructor or "")};border-radius:2px;vertical-align:middle;'
            'margin-right:8px"></span>'
        )
        driver_line = (
            f'<p style="margin:2px 0 0 11px;font-family:{_FONT_SANS};font-size:12px;'
            f'color:{_MUTED}">{html.escape(driver_name)}</p>'
        ) if driver_name else ""
        row_html.append(
            "<tr>"
            f'<td style="width:26px;padding:12px 0 12px 10px;{border}{wash}font-family:{_FONT_MONO};'
            f'font-size:14px;font-weight:600;color:{_ACCENT};vertical-align:top">{label}</td>'
            f'<td style="padding:12px 8px 12px 0;{border}{wash}vertical-align:top">'
            f'<p style="margin:0;font-family:{_FONT_SANS};font-size:15px;color:{_INK}">'
            f'{rule}{html.escape(constructor or "Unknown")}</p>'
            f"{driver_line}</td>"
            f'<td style="padding:12px 10px 12px 0;{border}{wash}text-align:right;'
            f'vertical-align:top">'
            f'<p style="margin:0;font-family:{_FONT_MONO};font-size:20px;font-weight:600;'
            f'color:{_darken(_team_color(constructor or ""))}">{html.escape(value)}</p>'
            f'<p style="margin:2px 0 0 0;font-family:{_FONT_SANS};font-size:11px;'
            f'color:{_MUTED}">{html.escape(caption)}</p>'
            "</td></tr>"
        )
    return (
        _PANEL_OPEN
        + _kicker("Practice")
        + f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border-top:1px solid {_HAIRLINE}">'
        + "".join(row_html)
        + "</table></div>"
    )


def _qualifying_html(quali: QualiInsight | None) -> str:
    if quali is None:
        return ""
    header = _clean(quali.header)
    body = _emphasize_numbers(_clean(_first_sentence(quali.explanation_email)))
    team_label = ""
    if quali.team:
        rule = (
            f'<span style="display:inline-block;width:3px;height:13px;background:'
            f'{_team_color(quali.team)};border-radius:2px;vertical-align:middle;'
            'margin-right:6px"></span>'
        )
        team_label = (
            f'<p style="margin:0 0 6px 0;font-family:{_FONT_MONO};font-size:12px;'
            f'letter-spacing:0.05em;text-transform:uppercase;color:{_MUTED}">'
            f"{rule}{html.escape(quali.team)}</p>"
        )
    # A team-tinted card background (stronger than the row-wash's 0.09, since this is the
    # whole card, not a strip between neighbours) instead of plain cream -- gives this card a
    # colored identity tied to the team it's actually about.
    panel_open = (
        f'<div style="background:{_team_color_alpha(quali.team, 0.12) if quali.team else _SURFACE};'
        f'border:1.5px solid {_INK};box-shadow:4px 4px 0 {_INK};border-radius:2px;padding:24px;'
        'margin:0 0 20px 0">'
    )
    return (
        panel_open
        + team_label
        + f'<h2 style="margin:0 0 8px 0;font-family:{_FONT_DISPLAY};font-size:21px;'
        f'letter-spacing:-0.01em;font-weight:600;color:{_INK}">{header}</h2>'
        + f'<p style="margin:0;font-size:15px;line-height:1.6;font-family:{_FONT_SANS};'
        f'color:{_INK}">{body}</p>'
        "</div>"
    )


def render_email(
    weekend: RaceWeekend,
    insights: list[Insight],
    base_url: str,
    *,
    winner: dict | None = None,
    next_race: dict | None = None,
    pace_spread: dict | None = None,
    practice: dict | None = None,
    quali_insight: QualiInsight | None = None,
) -> str:
    cta_url = f"{base_url.rstrip('/')}/weekends/{weekend.year}/{weekend.round}"
    event_name = html.escape(weekend.event_name)
    preheader_text, opener_html = _opener_html(winner, pace_spread)
    practice_section = _section_heading("Fast out the gates") + _practice_html(practice) if practice else ""
    qualifying_section = (
        _section_heading("Setting the grid") + _qualifying_html(quali_insight) if quali_insight else ""
    )

    cards = []
    for i, ins in enumerate(insights, start=1):
        header = _clean(ins.header)
        body = _emphasize_numbers(_clean(_first_sentence(ins.explanation_email)))
        # Team-colored border when the insight has a team on it, falling back to the shared
        # ink border for the rare row that doesn't (an un-backfilled or genuinely ambiguous
        # older insight).
        border_color = _team_color(ins.team) if ins.team else _INK
        card_open = (
            f'<div style="background:{_SURFACE};border:1.5px solid {border_color};'
            f'box-shadow:4px 4px 0 {_INK};border-radius:2px;padding:24px;margin:0 0 20px 0">'
        )
        cards.append(
            card_open
            + f'<p style="margin:0 0 6px 0;font-family:{_FONT_MONO};font-size:12px;'
            f'letter-spacing:0.1em;color:{_ACCENT}">0{i}</p>'
            f'<h2 style="margin:0 0 8px 0;font-family:{_FONT_DISPLAY};font-size:21px;'
            f'letter-spacing:-0.01em;font-weight:600;color:{_INK}">{header}</h2>'
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
    # A quiet sign-off before the legal line -- the email stopped cold at copyright/unsubscribe
    # before this, with no acknowledgment of the reader. Understated on purpose: no joke, no
    # exclamation point, matching the plain-broadcaster voice the insight prose itself holds to.
    sign_off = (
        f'<p style="margin:20px 0 0 0;font-family:{_FONT_SANS};font-size:13px;line-height:1.6;'
        f'color:{_INK}">See you after the next session.</p>'
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
        f'<p style="margin:0 0 28px 0;text-align:center;font-family:{_FONT_MONO};font-size:16px;'
        f'letter-spacing:0.16em;text-transform:uppercase;color:{_ACCENT}">{event_name}</p>'
        + opener_html
        + practice_section
        + qualifying_section
        + _section_heading("Here’s your three insights")
        + "".join(cards)
        + _pace_spread_html(pace_spread)
        + f'<p style="margin:0;font-family:{_FONT_SANS};font-size:15px;line-height:1.6;'
        f'color:{_INK}">This is a fraction of what’s in the full weekend analysis: tyre '
        "degradation by compound, sector dominance, qualifying car character, and the "
        "complete pace ranking.</p>"
        + f'<a href="{html.escape(cta_url)}" style="display:block;box-sizing:border-box;'
        'width:100%;margin-top:20px;padding:13px 24px;'
        f"background:{_ACCENT};color:{_ACCENT_INK};text-decoration:none;text-align:center;"
        f'border-radius:2px;font-family:{_FONT_SANS};font-size:18px;font-weight:600">'
        "Read the full analysis.</a>"
        + next_race_block
        + methodology
        + sign_off
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
    pace_spread: dict | None = None,
    practice: dict | None = None,
    quali_insight: QualiInsight | None = None,
) -> str:
    """Plain-text sibling of render_email for the multipart/alternative text part sending
    infrastructure (and some spam filters) expect alongside the HTML. Real driver/team/circuit
    names never contain HTML-special characters, so reusing render_email's already-"escaped"
    opener text here is safe -- html.escape is a no-op on this domain's inputs."""
    cta_url = f"{base_url.rstrip('/')}/weekends/{weekend.year}/{weekend.round}"
    opener_text, _ = _opener_html(winner, pace_spread)

    lines = [f"TELOGIFY · {weekend.event_name}", "", opener_text, ""]

    if practice is not None:
        lines.append("FAST OUT THE GATES")
        lines.append("")
        for sector, constructor, driver, margin, _best_time_s in practice["sectors"]:
            driver_bit = f" ({_full_driver_name(driver)})" if driver else ""
            clear_bit = f", {margin:.3f}s clear" if margin is not None else ""
            lines.append(f"  S{sector}: {constructor}{driver_bit}{clear_bit}")
        top_constructor = practice["top_speed_constructor"]
        driver_name = _full_driver_name(practice["top_speed_driver"])
        kmh = practice["top_speed_kmh"]
        lines.append(
            f"  TS: {top_constructor} ({driver_name}), {kmh:.0f} km/h ({kmh * 0.621371:.0f} mph)"
        )
        lines.append("")

    if quali_insight is not None:
        lines.append("SETTING THE GRID")
        lines.append("")
        header = strip_em_dashes(quali_insight.header) or ""
        body = strip_em_dashes(_first_sentence(quali_insight.explanation_email)) or ""
        lines.append(header)
        lines.append(body)
        lines.append("")

    lines.append("HERE'S YOUR THREE INSIGHTS")
    lines.append("")
    for i, ins in enumerate(insights, start=1):
        header = strip_em_dashes(ins.header) or ""
        body = strip_em_dashes(_first_sentence(ins.explanation_email)) or ""
        lines.append(f"{i:02d}. {header}")
        lines.append(body)
        lines.append("")

    if pace_spread is not None:
        lines.append("PACE SPREAD - CONSTRUCTORS")
        lines.append(
            f"{pace_spread['fastest']} set the pace this weekend. Here's how far back the "
            "next three fell, per lap."
        )
        for name, gap in pace_spread["rows"]:
            lines.append(f"  {name}: {gap}")
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
        length_km = next_race.get("length_km")
        length_bit = f", {length_km:.3f} km circuit" if length_km is not None else ""
        lines.append(f"NEXT RACE - ROUND {next_race['round']}")
        lines.append(f"{next_race['name']}{place}, {when}{length_bit}")
        lines.append("")

    lines.append(
        "Methodology inputs come from Mirco Bartolozzi (@fdataanalysis), covering clean-air "
        "filtering, fuel correction, and the ERS depletion signal. Timing data comes from FastF1."
    )
    lines.append("")
    lines.append("See you after the next session.")
    lines.append("")
    lines.append(f"© {weekend.year} Tanish Misra")
    lines.append(f"Unsubscribe: {base_url.rstrip('/')}/unsubscribe")

    return "\n".join(lines)


# Neubrutalist design: its own palette/type voice (near-black ink, thick borders, hard offset
# shadows, a monospace body for a "data sheet/zine" feel), reusing render_email's shared
# helpers (_full_driver_name, _clean, _first_sentence, _emphasize_numbers, _team_color,
# _darken) and email-safety conventions (inline styles only, role="presentation" tables, no
# <style>/classes/flexbox/custom fonts) throughout. Section order matches render_email exactly.
_NB_INK = "#0a0a0a"
_NB_BG = "#f2f2ea"
_NB_SURFACE = "#ffffff"
_NB_ACCENT = "#E10600"
_NB_YELLOW = "#FFE500"
_NB_MUTED = "#5c5c5c"
_NB_FONT_DISPLAY = "'Arial Black','Franklin Gothic Bold',Impact,sans-serif"
_NB_FONT_BODY = "'Courier New',Courier,monospace"


def _nb_panel_open(border_color: str = _NB_INK, *, margin: str = "0 0 20px 0") -> str:
    return (
        f'<div style="background:{_NB_SURFACE};border:3px solid {border_color};'
        f'box-shadow:6px 6px 0 {_NB_INK};padding:22px;margin:{margin}">'
    )


def _nb_section_title(text: str) -> str:
    return (
        f'<p style="margin:36px 0 14px 0;display:inline-block;background:{_NB_INK};color:#fff;'
        f'font-family:{_NB_FONT_DISPLAY};font-size:20px;font-weight:800;padding:5px 12px">{text}</p>'
    )


def _nb_practice_html(practice: dict | None) -> str:
    if practice is None:
        return ""
    rows = []
    for sector, constructor, driver, _margin, best_time_s in practice["sectors"]:
        driver_name = _full_driver_name(driver) if driver else None
        value = f"{best_time_s:.3f}s" if best_time_s is not None else "—"
        rows.append((f"S{sector}", constructor, driver_name, value))
    kmh = practice["top_speed_kmh"]
    mph = kmh * 0.621371
    rows.append(
        ("TS", practice["top_speed_constructor"], _full_driver_name(practice["top_speed_driver"]),
         f"{kmh:.0f} km/h ({mph:.0f} mph)")
    )
    row_html = []
    for label, constructor, driver_name, value in rows:
        rule = (
            f'<span style="display:inline-block;width:4px;height:14px;background:'
            f'{_team_color(constructor or "")};margin-right:8px;vertical-align:middle"></span>'
        )
        driver_bit = f" &middot; {html.escape(driver_name)}" if driver_name else ""
        row_html.append(
            '<tr>'
            f'<td style="padding:10px 0;border-bottom:2px dashed {_NB_INK}55;font-family:'
            f'{_NB_FONT_DISPLAY};font-size:13px;color:{_NB_INK};vertical-align:top">{label}</td>'
            f'<td style="padding:10px 8px;border-bottom:2px dashed {_NB_INK}55;font-family:'
            f'{_NB_FONT_BODY};font-size:14px;color:{_NB_INK}">{rule}{html.escape(constructor or "Unknown")}'
            f'{driver_bit}</td>'
            f'<td style="padding:10px 0;border-bottom:2px dashed {_NB_INK}55;text-align:right;'
            f'font-family:{_NB_FONT_DISPLAY};font-size:16px;color:{_NB_ACCENT};white-space:nowrap">'
            f'{html.escape(value)}</td>'
            '</tr>'
        )
    return (
        _nb_panel_open()
        + f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
        + "".join(row_html)
        + "</table></div>"
    )


def _nb_qualifying_html(quali: QualiInsight | None) -> str:
    if quali is None:
        return ""
    header = _clean(quali.header)
    body = _emphasize_numbers(_clean(_first_sentence(quali.explanation_email)))
    team_label = ""
    if quali.team:
        team_label = (
            f'<p style="margin:0 0 8px 0;display:inline-block;background:{_NB_YELLOW};'
            f'font-family:{_NB_FONT_DISPLAY};font-size:11px;padding:2px 8px;color:{_NB_INK}">'
            f'{html.escape(quali.team.upper())}</p>'
        )
    border = _team_color(quali.team) if quali.team else _NB_INK
    return (
        _nb_panel_open(border)
        + team_label
        + f'<h2 style="margin:0 0 8px 0;font-family:{_NB_FONT_DISPLAY};font-size:20px;'
        f'color:{_NB_INK}">{header}</h2>'
        + f'<p style="margin:0;font-size:14px;line-height:1.6;font-family:{_NB_FONT_BODY};'
        f'color:{_NB_INK}">{body}</p>'
        "</div>"
    )


def _nb_pace_spread_html(pace_spread: dict | None) -> str:
    if pace_spread is None:
        return ""
    fastest = html.escape(pace_spread["fastest"])
    row_html = []
    for name, gap in pace_spread["rows"]:
        color = _team_color(name)
        row_html.append(
            '<tr>'
            f'<td style="padding:10px 0;border-bottom:2px dashed {_NB_INK}55;font-family:'
            f'{_NB_FONT_BODY};font-size:14px;color:{_NB_INK}">'
            f'<span style="display:inline-block;width:11px;height:11px;background:{color};'
            f'border:2px solid {_NB_INK};margin-right:8px;vertical-align:middle"></span>'
            f'{html.escape(name)}</td>'
            f'<td style="padding:10px 0;border-bottom:2px dashed {_NB_INK}55;text-align:right;'
            f'font-family:{_NB_FONT_DISPLAY};font-size:18px;color:{color}">{html.escape(gap)}</td>'
            '</tr>'
        )
    return (
        _nb_panel_open()
        + f'<p style="margin:0 0 14px 0;font-family:{_NB_FONT_BODY};font-size:13px;'
        f'color:{_NB_INK}">{fastest} set the pace this weekend. Gap per lap, race pace:</p>'
        + '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
        + "".join(row_html)
        + "</table></div>"
    )


def _nb_next_race_html(next_race: dict | None) -> str:
    if next_race is None:
        return ""
    days = next_race["days"]
    when = "TODAY" if days == 0 else ("TOMORROW" if days == 1 else f"{days} DAYS")
    stats = f'<span style="font-family:{_NB_FONT_DISPLAY};font-size:22px;color:{_NB_YELLOW}">{html.escape(when)}</span>'
    length_km = next_race.get("length_km")
    if length_km is not None:
        stats += (
            f'<span style="font-family:{_NB_FONT_DISPLAY};font-size:22px;color:{_NB_YELLOW};'
            f'margin-left:22px">{length_km:.3f} KM</span>'
        )
    return (
        f'<div style="background:{_NB_INK};border:3px solid {_NB_INK};box-shadow:6px 6px 0 '
        f'{_NB_ACCENT};padding:22px;margin:32px 0 20px 0">'
        f'<p style="margin:0 0 8px 0;display:inline-block;background:{_NB_ACCENT};color:#fff;'
        f'font-family:{_NB_FONT_DISPLAY};font-size:11px;padding:3px 9px">'
        f'NEXT UP &middot; ROUND {next_race["round"]}</p>'
        f'<h3 style="margin:8px 0 4px 0;font-family:{_NB_FONT_DISPLAY};font-size:22px;color:#fff">'
        f'{html.escape(next_race["name"])}</h3>'
        + (
            f'<p style="margin:0 0 14px 0;font-family:{_NB_FONT_BODY};font-size:13px;color:#ccc">'
            f'{html.escape(next_race["place"])}</p>' if next_race.get("place") else ""
        )
        + f'<p style="margin:0">{stats}</p></div>'
    )


def render_email_neubrutalist(
    weekend: RaceWeekend,
    insights: list[Insight],
    base_url: str,
    *,
    winner: dict | None = None,
    next_race: dict | None = None,
    pace_spread: dict | None = None,
    practice: dict | None = None,
    quali_insight: QualiInsight | None = None,
) -> str:
    cta_url = f"{base_url.rstrip('/')}/weekends/{weekend.year}/{weekend.round}"
    event_name = html.escape(weekend.event_name)
    preheader_text, _ = _opener_html(winner, pace_spread)

    practice_section = (
        _nb_section_title("FAST OUT THE GATES") + _nb_practice_html(practice) if practice else ""
    )
    qualifying_section = (
        _nb_section_title("QUALIFYING HOUR") + _nb_qualifying_html(quali_insight)
        if quali_insight else ""
    )

    cards = []
    for i, ins in enumerate(insights, start=1):
        header = _clean(ins.header)
        body = _emphasize_numbers(_clean(_first_sentence(ins.explanation_email)))
        border = _team_color(ins.team) if ins.team else _NB_INK
        num_badge = (
            f'<span style="display:inline-block;width:34px;height:34px;line-height:34px;'
            f'text-align:center;background:{_NB_YELLOW};border:3px solid {_NB_INK};'
            f'border-radius:50%;font-family:{_NB_FONT_DISPLAY};font-size:15px;color:{_NB_INK};'
            f'margin-bottom:10px">{i}</span>'
        )
        cards.append(
            _nb_panel_open(border)
            + num_badge
            + f'<h2 style="margin:0 0 8px 0;font-family:{_NB_FONT_DISPLAY};font-size:19px;'
            f'color:{_NB_INK}">{header}</h2>'
            f'<p style="margin:0;font-size:14px;line-height:1.65;font-family:{_NB_FONT_BODY};'
            f'color:{_NB_INK}">{body}</p>'
            "</div>"
        )

    cta = (
        f'<a href="{html.escape(cta_url)}" style="display:block;box-sizing:border-box;'
        'width:100%;margin-top:20px;padding:16px 20px;text-align:center;text-decoration:none;'
        f'background:{_NB_ACCENT};color:#fff;border:3px solid {_NB_INK};box-shadow:6px 6px 0 '
        f'{_NB_INK};font-family:{_NB_FONT_DISPLAY};font-size:17px">READ THE FULL ANALYSIS</a>'
    )
    methodology = (
        f'<p style="margin:24px 0 0 0;font-family:{_NB_FONT_BODY};font-size:11px;line-height:1.6;'
        f'color:{_NB_MUTED}">Methodology inputs come from Mirco Bartolozzi (@fdataanalysis), '
        "covering clean-air filtering, fuel correction, and the ERS depletion signal. "
        "Timing data comes from FastF1.</p>"
    )
    sign_off = (
        f'<p style="margin:20px 0 0 0;font-family:{_NB_FONT_BODY};font-size:13px;color:{_NB_INK}">'
        "See you after the next session.</p>"
    )
    copyright_line = (
        f'<p style="margin:20px 0 0 0;font-family:{_NB_FONT_BODY};font-size:11px;color:{_NB_MUTED}">'
        f"&copy; {weekend.year} Tanish Misra &middot; "
        f'<a href="{html.escape(base_url.rstrip("/"))}/unsubscribe" style="color:{_NB_MUTED}">'
        "Unsubscribe</a></p>"
    )

    return (
        f'<div style="display:none;max-height:0;overflow:hidden;opacity:0">{preheader_text}</div>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="background:{_NB_BG}"><tr><td align="center" style="padding:32px 16px">'
        f'<div style="max-width:560px;margin:0 auto;text-align:left;background:{_NB_SURFACE};'
        f'border:3px solid {_NB_INK};padding:28px 24px">'
        '<div style="margin:0 0 20px 0;text-align:center">'
        '<svg width="40" height="40" viewBox="0 0 32 32" fill="none" stroke-width="3" '
        'stroke-linecap="round" stroke-linejoin="round" '
        'style="display:inline-block;vertical-align:middle">'
        f'<path d="M2 16 L6 7 L10 25 L13 11 L16 20 L18 16" stroke="{_NB_INK}"></path>'
        f'<path d="M18 16 L30 16" stroke="{_NB_ACCENT}"></path>'
        "</svg>"
        f'<span style="display:inline-block;vertical-align:middle;margin-left:10px;'
        f'font-family:{_NB_FONT_DISPLAY};font-size:34px;color:{_NB_INK}">telo'
        f'<span style="color:{_NB_ACCENT}">gify</span></span></div>'
        f'<p style="margin:0 0 24px 0;text-align:center;font-family:{_NB_FONT_BODY};font-size:14px;'
        f'letter-spacing:0.08em;text-transform:uppercase;color:{_NB_MUTED}">{event_name}</p>'
        + f'<p style="margin:0 0 24px 0;font-family:{_NB_FONT_BODY};font-size:15px;line-height:1.6;'
        f'color:{_NB_INK}">{preheader_text}</p>'
        + practice_section
        + qualifying_section
        + _nb_section_title("THE 3 INSIGHTS")
        + "".join(cards)
        + _nb_pace_spread_html(pace_spread)
        + cta
        + _nb_next_race_html(next_race)
        + methodology
        + sign_off
        + copyright_line
        + "</div></td></tr></table>"
    )


# Conversational design: an iMessage-style chat thread. Reuses render_email's own palette
# tokens (_INK, _MUTED, _FONT_SANS, _FONT_MONO, _FONT_DISPLAY, _ACCENT) for the masthead and
# body text -- this design's own identity is structural (bubbles), not a different typographic
# voice -- plus a few bubble-specific surface colors. Same email-safety conventions as
# render_email throughout (inline styles, role="presentation" tables, no <style>/classes).
_CV_BG = "#EFEEE9"
_CV_BUBBLE = "#FFFFFF"
_CV_BUBBLE_BORDER = "#E4E2DB"
_CV_SENT_INK = "#FFF6F5"


def _cv_bubble(content_html: str, *, max_width: str = "420px") -> str:
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 8px 0">'
        f'<tr><td style="background:{_CV_BUBBLE};border:1px solid {_CV_BUBBLE_BORDER};'
        f'border-radius:16px 16px 16px 4px;padding:11px 15px;max-width:{max_width};'
        f'font-family:{_FONT_SANS};font-size:15px;line-height:1.42;color:{_INK}">{content_html}'
        "</td></tr></table>"
    )


def _cv_data_bubble(rows_html: str) -> str:
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 8px 0">'
        f'<tr><td style="background:{_CV_BUBBLE};border:1px solid {_CV_BUBBLE_BORDER};'
        'border-radius:16px 16px 16px 4px;padding:13px 16px;max-width:460px">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows_html}'
        "</table></td></tr></table>"
    )


def _cv_data_row(label_html: str, value: str) -> str:
    return (
        "<tr>"
        f'<td style="padding:5px 0;border-bottom:1px solid #F0EFEA;font-family:{_FONT_SANS};'
        f'font-size:14px;color:{_INK}">{label_html}</td>'
        f'<td style="padding:5px 0;border-bottom:1px solid #F0EFEA;text-align:right;'
        f'font-family:{_FONT_MONO};font-size:15px;font-weight:600;color:{_INK};white-space:nowrap">'
        f"{html.escape(value)}</td>"
        "</tr>"
    )


def _cv_insight_bubble(number: str, team: str | None, header: str, body: str) -> str:
    color = _team_color(team) if team else _MUTED
    tag = (
        f'<span style="display:inline-block;font-family:{_FONT_MONO};font-size:10.5px;'
        f'font-weight:600;letter-spacing:0.06em;color:{color};border:1.5px solid {color};'
        f'border-radius:5px;padding:2px 8px;margin-bottom:8px">{number}</span><br>'
    )
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 8px 0">'
        f'<tr><td style="background:{_CV_BUBBLE};border:1px solid {_CV_BUBBLE_BORDER};'
        'border-radius:16px 16px 16px 4px;padding:14px 16px;max-width:460px">'
        f"{tag}"
        f'<p style="margin:0 0 5px 0;font-weight:700;font-size:15.5px;line-height:1.32;'
        f'font-family:{_FONT_SANS};color:{_INK}">{header}</p>'
        f'<p style="margin:0;font-size:14px;line-height:1.48;font-family:{_FONT_SANS};'
        f'color:#4A443E">{body}</p>'
        "</td></tr></table>"
    )


def render_email_conversational(
    weekend: RaceWeekend,
    insights: list[Insight],
    base_url: str,
    *,
    winner: dict | None = None,
    next_race: dict | None = None,
    pace_spread: dict | None = None,
    practice: dict | None = None,
    quali_insight: QualiInsight | None = None,
    now: datetime | None = None,
) -> str:
    now = now or datetime.utcnow()
    cta_url = f"{base_url.rstrip('/')}/weekends/{weekend.year}/{weekend.round}"
    event_name = html.escape(weekend.event_name)
    preheader_text, _ = _opener_html(winner, pace_spread)

    bubbles = [_cv_bubble("Hey, the race is done! Results are in."), _cv_bubble(preheader_text)]

    if practice is not None:
        bubbles.append(_cv_bubble("First up, practice:"))
        rows = []
        for sector, constructor, driver, _margin, best_time_s in practice["sectors"]:
            driver_bit = f"<span style=\"color:{_MUTED};font-size:12.5px;display:block\">" \
                f"{html.escape(constructor or 'Unknown')} ({html.escape(_full_driver_name(driver))})</span>" \
                if driver else html.escape(constructor or "Unknown")
            value = f"{best_time_s:.3f}s" if best_time_s is not None else "—"
            rows.append(_cv_data_row(f"S{sector}<br>{driver_bit}", value))
        kmh = practice["top_speed_kmh"]
        rows.append(_cv_data_row(
            f"Top speed<br><span style=\"color:{_MUTED};font-size:12.5px\">"
            f"{html.escape(practice['top_speed_constructor'] or 'Unknown')} "
            f"({html.escape(_full_driver_name(practice['top_speed_driver']))})</span>",
            f"{kmh:.0f} km/h",
        ))
        bubbles.append(_cv_data_bubble("".join(rows)))

    if quali_insight is not None:
        bubbles.append(_cv_bubble("And from qualifying, one thing stood out:"))
        header = _clean(quali_insight.header)
        body = _emphasize_numbers(_clean(_first_sentence(quali_insight.explanation_email)))
        bubbles.append(_cv_insight_bubble("QUALIFYING", quali_insight.team, header, body))

    if pace_spread is not None:
        bubbles.append(_cv_bubble("Onto the race. Here's the race-pace picture:"))
        fastest = html.escape(pace_spread["fastest"])
        rows = [_cv_data_row(f"{fastest}<br><span style=\"color:{_MUTED};font-size:12.5px\">"
                              "race pace, fastest</span>", "leader")]
        for name, gap in pace_spread["rows"]:
            rows.append(_cv_data_row(html.escape(name), gap))
        bubbles.append(_cv_data_bubble("".join(rows)))
        bubbles.append(_cv_bubble(
            "(And by the way, those are gaps to the fastest car, per lap.)", max_width="340px"
        ))

    if insights:
        bubbles.append(_cv_bubble(
            "Here are the three things worth knowing from the race itself."
        ))
        for i, ins in enumerate(insights, start=1):
            header = _clean(ins.header)
            body = _emphasize_numbers(_clean(_first_sentence(ins.explanation_email)))
            bubbles.append(_cv_insight_bubble(f"0{i}", ins.team, header, body))

    bubbles.append(_cv_bubble("That's the recap. Full breakdown has more telemetry if you want it."))
    bubbles.append(
        '<table role="presentation" align="right" cellpadding="0" cellspacing="0" '
        'style="margin:18px 0 8px auto">'
        f'<tr><td style="background:{_ACCENT};border-radius:16px 16px 4px 16px;padding:11px 16px;'
        f'max-width:300px"><a href="{html.escape(cta_url)}" style="font-family:{_FONT_SANS};'
        f'font-size:15px;font-weight:600;color:{_CV_SENT_INK};text-decoration:none">'
        "Read the full analysis</a></td></tr></table>"
        # align="right" makes the table float in most renderers; clear it so the next bubble
        # drops below instead of wrapping alongside it.
        '<div style="clear:both"></div>'
    )
    bubbles.append(_cv_bubble("Yesss, love that."))

    if next_race is not None:
        days = next_race["days"]
        when = "today" if days == 0 else ("tomorrow" if days == 1 else f"{days} days")
        length_km = next_race.get("length_km")
        length_bit = f" on a {length_km:.3f} km circuit" if length_km is not None else ""
        place_bit = f" in {html.escape(next_race['place'])}" if next_race.get("place") else ""
        bubbles.append(_cv_bubble(
            f"Next up: the {html.escape(next_race['name'])}{place_bit}, {when} away{length_bit}."
        ))

    bubbles.append(_cv_bubble("See you after the next session!"))

    footer = (
        f'<p style="margin:30px 0 0 0;font-size:11.5px;color:{_MUTED};line-height:1.7;'
        f'font-family:{_FONT_SANS}">Methodology inputs come from Mirco Bartolozzi '
        "(@fdataanalysis), covering clean-air filtering, fuel correction, and the ERS "
        "depletion signal. Timing data comes from FastF1.<br>"
        f"&copy; {weekend.year} Tanish Misra &middot; "
        f'<a href="{html.escape(base_url.rstrip("/"))}/unsubscribe" style="color:{_MUTED}">'
        "Unsubscribe</a></p>"
    )

    day_chip = (
        '<div style="text-align:center;margin:18px 0 16px 0">'
        f'<span style="display:inline-block;background:rgba(0,0,0,0.05);color:{_MUTED};'
        f'font-size:11px;font-weight:600;padding:4px 12px;border-radius:20px;'
        f'letter-spacing:0.02em;font-family:{_FONT_SANS}">{now.strftime("%A").upper()}</span>'
        "</div>"
    )

    return (
        f'<div style="display:none;max-height:0;overflow:hidden;opacity:0">{preheader_text}</div>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="background:{_CV_BG}"><tr><td align="center" style="padding:32px 16px">'
        f'<div style="max-width:480px;margin:0 auto;background:#fff;border:1px solid '
        f'{_CV_BUBBLE_BORDER};border-radius:20px;padding:28px 20px;text-align:left">'
        '<div style="margin:0 0 4px 0;text-align:center">'
        '<span style="display:inline-block;border-bottom:2px solid ' + _ACCENT + ';padding-bottom:6px">'
        '<svg width="34" height="34" viewBox="0 0 32 32" fill="none" stroke-width="3" '
        'stroke-linecap="round" stroke-linejoin="round" '
        'style="display:inline-block;vertical-align:middle">'
        f'<path d="M2 16 L6 7 L10 25 L13 11 L16 20 L18 16" stroke="{_INK}"></path>'
        f'<path d="M18 16 L30 16" stroke="{_ACCENT}"></path>'
        "</svg>"
        f'<span style="display:inline-block;vertical-align:middle;margin-left:10px;'
        f'font-family:{_FONT_DISPLAY};font-size:34px;font-weight:400;color:{_INK}">Telo'
        f'<span style="color:{_ACCENT}">gify</span></span></span></div>'
        f'<p style="margin:0;text-align:center;font-family:{_FONT_MONO};font-size:11px;'
        f'letter-spacing:0.1em;text-transform:uppercase;color:{_MUTED}">{event_name}</p>'
        + day_chip
        + "".join(bubbles)
        + footer
        + "</div></td></tr></table>"
    )


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
    place = ev.location or ""
    return {
        "round": ev.round,
        "name": ev.name,
        "place": place,
        "days": days,
        "length_km": _CIRCUIT_LENGTH_KM.get(ev.name),
    }


def _load_pace_spread_constructors(db: Session, weekend_id: int) -> dict | None:
    """Real per-constructor race-pace gaps: the same canonical median metric as the /pace
    chart and constructor ranking (race_pace.py's constructor_median_gaps), fuel-corrected
    green-flag laps. None when there isn't enough race data to compare constructors."""
    sessions = db.exec(select(SessionRow).where(SessionRow.weekend_id == weekend_id)).all()
    dc_map = _driver_constructor_map(db, [s.id for s in sessions])
    stint_dicts = _race_stints_as_dicts(db, sessions, dc_map)
    gaps = constructor_median_gaps(stint_dicts)
    if len(gaps) < 2:
        return None
    ranked = sorted(gaps.items(), key=lambda kv: kv[1])
    fastest = ranked[0][0]
    rows = [(team, f"+{gap:.3f}s") for team, gap in ranked[1:4]]
    return {"fastest": fastest, "rows": rows}


def _load_practice_summary(db: Session, weekend_id: int) -> dict | None:
    """Sector dominance (S1-3) and top speed across FP1-3/SQ -- the same indicative-session
    convention and pure functions (analysis/sectors.py) the site's own /sectors and
    /topspeeds endpoints use. None when there's no indicative-session data yet."""
    sessions = db.exec(select(SessionRow).where(SessionRow.weekend_id == weekend_id)).all()
    indicative = [s for s in sessions if s.session_type in _INDICATIVE_SESSIONS]
    if not indicative:
        return None
    dc_map = _driver_constructor_map(db, [s.id for s in sessions])

    sector_rows = [
        {"driver": r.driver, "sector": r.sector, "best_time_s": r.best_time_s, "session_type": s.session_type}
        for s in indicative
        for r in db.exec(select(SectorBest).where(SectorBest.session_id == s.id)).all()
    ]
    bests = best_across_sessions(sector_rows)
    enriched = [
        {"driver": b.driver, "sector": b.sector, "best_time_s": b.best_time_s, "constructor": dc_map.get(b.driver)}
        for b in bests
    ]
    dominance = sector_dominance(enriched)
    if not dominance:
        return None
    # sector_dominance aggregates to the constructor's best time; recover which driver actually
    # set it (an exact match, since that best_time_s came from this same enriched list).
    sectors = []
    for d in dominance:
        driver = next(
            (
                e["driver"] for e in enriched
                if e["sector"] == d.sector and e["constructor"] == d.constructor
                and e["best_time_s"] == d.best_time_s
            ),
            None,
        )
        sectors.append((d.sector, d.constructor, driver, d.margin_s, d.best_time_s))

    speed_rows = [
        {"driver": r.driver, "session_type": s.session_type, "max_speed_kmh": r.max_speed_kmh}
        for s in indicative
        for r in db.exec(select(StraightSegment).where(StraightSegment.session_id == s.id)).all()
        if r.max_speed_kmh is not None
    ]
    top_speeds = best_top_speeds(speed_rows)
    if not top_speeds:
        return None
    fastest_speed = max(top_speeds, key=lambda r: r["max_speed_kmh"])

    return {
        "sectors": sectors,
        "top_speed_driver": fastest_speed["driver"],
        "top_speed_constructor": dc_map.get(fastest_speed["driver"]),
        "top_speed_kmh": fastest_speed["max_speed_kmh"],
    }


def _load_quali_insight(db: Session, weekend_id: int) -> QualiInsight | None:
    """One of the (up to 2) LLM-written qualifying car-character insights, if any exist yet --
    slot 1, the primary one."""
    return db.exec(
        select(QualiInsight).where(QualiInsight.weekend_id == weekend_id).order_by(QualiInsight.slot)
    ).first()


def _load_extras(db: Session, weekend: RaceWeekend) -> dict:
    return {
        "winner": _load_winner(db, weekend.id),
        "next_race": _load_next_race(),
        "pace_spread": _load_pace_spread_constructors(db, weekend.id),
        "practice": _load_practice_summary(db, weekend.id),
        "quali_insight": _load_quali_insight(db, weekend.id),
    }


_DESIGNS = ("production", "neubrutalist", "conversational")
_RENDER_FNS = {
    "production": render_email,
    "neubrutalist": render_email_neubrutalist,
    "conversational": render_email_conversational,
}


def _choose_digest_design(history: list[str]) -> str:
    """history = digest_design values for weekends already sent, oldest -> newest. First-ever
    send is always production; every run of 3 consecutive sends contains each design exactly
    once; a design is never repeated on consecutive sends, including across a cycle boundary."""
    if not history:
        return "production"
    cycle_position = len(history) % 3
    used_this_cycle = set(history[-cycle_position:]) if cycle_position else set()
    candidates = [d for d in _DESIGNS if d not in used_this_cycle and d != history[-1]]
    return random.choice(candidates)


def _load_digest_history(db: Session) -> list[str]:
    weekends = db.exec(
        select(RaceWeekend)
        .where(RaceWeekend.digest_design.is_not(None))
        .order_by(RaceWeekend.year, RaceWeekend.round)
    ).all()
    return [w.digest_design for w in weekends]


def render_digest_preview(year: int, round: int, db: Session, design: str | None = None) -> str:
    """Render the digest HTML for local preview. Never touches RESEND_API_KEY, never writes to
    the DB -- safe to preview any design repeatedly without disturbing the real rotation
    history. `design` overrides; otherwise reuses the weekend's already-sent design if it has
    one, else falls back to "production"."""
    weekend, insights = _load_weekend_and_insights(year, round, db)
    chosen = design or weekend.digest_design or "production"
    render_fn = _RENDER_FNS[chosen]
    return render_fn(weekend, insights, settings.web_base_url, **_load_extras(db, weekend))


def send_digest(year: int, round: int, db: Session, recipients: list[str] | None = None) -> int:
    """Send the digest to subscribers (or `recipients`). Returns the number sent."""
    if not settings.resend_api_key:
        raise RuntimeError("RESEND_API_KEY is not set; cannot send the digest.")

    weekend, insights = _load_weekend_and_insights(year, round, db)

    if recipients is None:
        recipients = [s.email for s in db.exec(select(Subscriber)).all()]
    if not recipients:
        return 0

    # Pick+persist the design once, on the first real send for this weekend -- a re-send reuses
    # whatever was already chosen rather than re-rolling.
    if weekend.digest_design is None:
        weekend.digest_design = _choose_digest_design(_load_digest_history(db))
        db.add(weekend)
        db.commit()
        db.refresh(weekend)

    import resend

    resend.api_key = settings.resend_api_key
    extras = _load_extras(db, weekend)
    render_fn = _RENDER_FNS[weekend.digest_design]
    html_body = render_fn(weekend, insights, settings.web_base_url, **extras)
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
