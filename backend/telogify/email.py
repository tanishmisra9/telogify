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


# Ported from teamShortName in frontend/src/lib/teamColors.ts, for chip labels narrow enough to
# need a shortened team name (Conversational's race-pace chips).
_TEAM_SHORT = {
    "Red Bull Racing": "Red Bull", "Haas F1 Team": "Haas", "Williams Racing": "Williams",
    "Scuderia AlphaTauri": "AlphaTauri", "Kick Sauber": "Sauber",
    "Aston Martin": "AM", "Racing Bulls": "RB",
}


def _team_short_name(team: str) -> str:
    return _TEAM_SHORT.get(team, team)


def _team_color_alpha(team: str, alpha: float) -> str:
    """Ported from teamColorWithAlpha in teamColors.ts, used at 0.09 for the site's row-wash
    pattern (Results.tsx, SeasonPage.tsx, QualiCharacterTable.tsx, DegradationChart.tsx)."""
    hex_color = _team_color(team)
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


def _team_tint(team: str, alpha: float) -> str:
    """Opaque version of _team_color_alpha: blends the team color against white and returns a
    solid hex, not rgba. Needed wherever a semi-transparent background would otherwise blend
    with whatever sits directly behind it rather than the page -- e.g. Neubrutalist's
    shadow-box panels (_nb_shadow_box), where a real rgba tint would visibly pick up the black
    shadow layer immediately behind it instead of reading as a light tint."""
    hex_color = _team_color(team)
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    mix = lambda channel: round(channel * alpha + 255 * (1 - alpha))
    return f"#{mix(r):02x}{mix(g):02x}{mix(b):02x}"


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


# Neubrutalist design: near-literal port of the approved digest-v59.html comp (punk-zine
# collage -- torn strip, rotated stickers/tiles/cards, ransom-note headline, alternating
# insight-card shadows via real :nth-child, real Archivo Black/Space Mono webfonts). Returns a
# full standalone HTML document (doctype/head/style), not a body fragment like render_email --
# real webfonts and a dot-pattern canvas need a real <head>.
#
# Real send test (Resend -> real Gmail address) found Gmail (desktop webmail + iOS/Android,
# the overwhelming majority of recipients) strips or ignores: transform (no rotation, any
# platform), the left/right/top/bottom offsets a position:absolute element needs to actually
# be positioned, display:flex/grid, box-shadow (desktop webmail), inline <svg>, and CSS custom
# properties (var() references survive, :root declarations don't -- N/A here, Neubrutalist
# never used them, see the Conversational design's own note below for where this bit hardest).
# Verified against Context7's /hteumeuleu/caniemail. Grid/flex rows, the WINNER sticker, and
# the insight number badges are now table-based / normal-flow instead of relying on those
# properties; transform/box-shadow/clip-path stay in the stylesheet since Gmail ignores them
# for free and Apple Mail/Samsung Email/Thunderbird still render the fuller collage effect.
_NB_INK = "#0a0a0a"

_NB_FONTS_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link href="https://fonts.googleapis.com/css2?family=Archivo+Black&display=swap" rel="stylesheet">'
)

# Short, genuinely cross-platform-identical fallback stacks (attempt 4): the previous long
# chains ('Arial Black', Impact, 'Helvetica Neue', Roboto...) don't all exist on every
# platform, so desktop Gmail and the Gmail iOS app were landing on *different real fonts* once
# Archivo Black failed to load (it never does in Gmail -- no external <link> fetching), which
# read as inconsistent/careless rather than one deliberate design. Arial Bold (weight 700, not
# 900 -- Arial has no true black cut, so 900 either clamps inconsistently per engine or forces
# synthetic emboldening that also distorts Archivo Black itself where it does load) exists
# under that exact name on Windows/macOS/iOS; Android aliases it to Roboto Bold, visually close
# enough to read as the same design everywhere.
_NB_DISPLAY_FONT = "'Archivo Black', Arial, Helvetica, sans-serif"
# Attempt 5: body prose (insight/qualifying text, the sub-line) used to inherit a monospace
# base (Space Mono -> Courier New, since Space Mono never loads in Gmail either), which read
# as childish/unprofessional across multi-line paragraphs. The design's zine character already
# comes from the bold display headers, hard shadows, and yellow highlights -- not from mono --
# so prose moves to a plain, genuinely universal sans instead. No webfont at all here on
# purpose: it's supporting text, not part of the identity, so there's nothing to lose by
# skipping the swap-in delay/inconsistency entirely.
_NB_SANS_FONT = "Arial, Helvetica, sans-serif"


def _nb_shadow_box(
    inner_html: str,
    *,
    bg: str = "#fff",
    border_color: str = _NB_INK,
    border_width: str = "4px",
    shadow_color: str = _NB_INK,
    offset: int = 10,
    side: str = "right",
    inline: bool = False,
    box_class: str = "",
    box_style: str = "",
    wrapper_style: str = "",
) -> str:
    """Fakes a hard offset-shadow with two nested boxes instead of CSS box-shadow (dead on
    Gmail desktop webmail, Google-Workspace-account-only on iOS/Android): an outer div painted
    the shadow color, with the visible content box inset from it via ordinary positive margin,
    so the shadow color peeks out as a real color discontinuity. background-color and margin
    are both universally supported, unlike box-shadow -- this reads as actual depth instead of
    attempt 3's thick-border version, which tested as "looks like a mistake, not a design
    choice." `side` flips which edges the inset margin (and therefore the visible shadow) sits
    on, for the insight cards' alternating shadow direction."""
    display = "inline-block" if inline else "block"
    margin = f"0 {offset}px {offset}px 0" if side == "right" else f"0 0 {offset}px {offset}px"
    cls = f' class="{box_class}"' if box_class else ""
    return (
        f'<div style="display:{display};background:{shadow_color};{wrapper_style}">'
        f'<div{cls} style="background:{bg};border:{border_width} solid {border_color};margin:{margin};{box_style}">'
        f"{inner_html}"
        "</div></div>"
    )


def _nb_stamp(text_html: str, *, bg: str = "#E10600", inline: bool = True) -> str:
    return _nb_shadow_box(
        text_html, bg=bg, border_width="3px", offset=6, inline=inline,
        box_style=(
            f"color:#fff;font-family:{_NB_DISPLAY_FONT};font-weight:700;"
            "padding:10px 18px;font-size:15px;letter-spacing:0.02em;"
        ),
    )


_NB_STYLE = f"""
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; }}
  .page {{
    background: #f2f2ea radial-gradient(#00000012 1px, transparent 1px) 0 0/14px 14px;
    padding: 48px 16px 80px;
    font-family: {_NB_SANS_FONT};
    color: #0a0a0a;
  }}
  .sheet {{ width: 100%; max-width: 700px; margin: 0 auto; background: #fdfdfb; border: 1px solid #0a0a0a1a; padding: 40px 24px; }}
  .masthead {{ text-align: center; margin-bottom: 46px; padding-bottom: 40px; }}
  .masthead .wordmark {{ font-family: {_NB_DISPLAY_FONT}; font-weight: 700; font-size: 52px; line-height: 0.9; margin: 18px 0 0; letter-spacing: -0.01em; }}
  .masthead .wordmark span {{ color: #E10600; }}
  .masthead .rip {{ margin: 18px -16px 0; height: 20px; background: #0a0a0a; clip-path: polygon(0% 0%, 4% 100%, 9% 10%, 14% 100%, 19% 15%, 24% 100%, 29% 5%, 34% 100%, 39% 20%, 44% 100%, 49% 0%, 54% 100%, 59% 10%, 64% 100%, 69% 5%, 74% 100%, 79% 15%, 84% 100%, 89% 0%, 94% 100%, 100% 20%, 100% 100%, 0% 100%); }}
  .ransom {{ font-family: {_NB_DISPLAY_FONT}; font-weight: 700; line-height: 1.25; margin: 4px 0 0; }}
  .ransom .a {{ font-size: 22px; }}
  .ransom .b {{ font-size: 44px; color: #E10600; }}
  .ransom .c {{ font-size: 30px; background: #0a0a0a; color: #fff; padding: 2px 6px; }}
  .ransom .d {{ font-size: 22px; }}
  .ransom .e {{ font-size: 38px; text-decoration: underline wavy #27F4D2 4px; text-underline-offset: 6px; }}
  .sub {{ font-size: 14px; line-height: 1.6; margin-top: 14px; max-width: 56ch; }}
  .sub b {{ background: #FFE500; padding: 0 3px; }}
  .section-title {{ font-family: {_NB_DISPLAY_FONT}; font-weight: 700; font-size: 22px; display: inline-block; background: #0a0a0a; color: #fff; padding: 6px 14px; margin: 0 0 18px; }}
  .swatch {{ display:inline-block; width:11px; height:11px; margin-right:8px; border:2px solid #0a0a0a; vertical-align:middle; }}
  .practice-tile-inner {{ font-size: 13px; }}
  .practice-tile-inner .lbl {{ font-family: {_NB_DISPLAY_FONT}; font-weight: 700; font-size: 11px; background: #FFE500; color: #fff; display: inline-block; padding: 1px 6px; margin-bottom: 6px; }}
  .practice-tile-inner .val {{ font-family: {_NB_DISPLAY_FONT}; font-weight: 700; font-size: 20px; margin: 2px 0; }}
  .quali-inner .lbl {{ font-family: {_NB_DISPLAY_FONT}; font-weight: 700; font-size: 12px; background: #0a0a0a; color: #fff; display: inline-block; padding: 3px 10px; }}
  .quali-inner h3 {{ font-family: {_NB_DISPLAY_FONT}; font-weight: 700; font-size: 21px; margin: 12px 0 8px; line-height: 1.15; }}
  .quali-inner p {{ font-size: 14px; line-height: 1.6; margin: 0; max-width: 54ch; }}
  .insight-inner h3 {{ font-family: {_NB_DISPLAY_FONT}; font-weight: 700; font-size: 19px; margin: 0 0 8px; line-height: 1.2; }}
  .insight-inner p {{ font-size: 14px; line-height: 1.65; margin: 0; }}
  .num-flag {{ display: inline-block; font-family: {_NB_DISPLAY_FONT}; font-weight: 700; font-size: 22px; color: #0a0a0a; background: #FFE500; border: 3px solid #0a0a0a; width: 38px; height: 38px; line-height: 32px; text-align: center; border-radius: 50%; }}
  .next-race-inner h3 {{ font-family: {_NB_DISPLAY_FONT}; font-weight: 700; font-size:24px; margin:12px 0 6px; }}
  .next-race-inner .lbl {{ font-family: {_NB_DISPLAY_FONT}; font-weight: 700; font-size:11px; color:#fff; background:#E10600; padding:3px 9px; display:inline-block; }}
  .next-race-inner .stats {{ margin-top:14px; font-size:13px; }}
  .next-race-inner .stats b {{ font-family: {_NB_DISPLAY_FONT}; font-weight: 700; font-size:22px; color:#E10600; display:block; }}
  footer {{ font-size: 12px; line-height: 1.8; color: #0a0a0a99; border-top: 3px solid #0a0a0a; padding-top: 18px; }}
  @media (prefers-color-scheme: dark) {{
    /* Best-effort only (email.py:626 header note): Gmail's iOS/Android apps -- where the
       worst dark-mode reports came from -- ignore this media query outright and run their
       own automatic color inversion instead, which nothing here can override. This helps the
       clients that DO respect it (Apple Mail, Samsung Email, Gmail desktop webmail). Panel
       backgrounds/borders are set inline per-instance by _nb_shadow_box, so they're left as
       white cards floating on the darkened page rather than fought with !important overrides
       -- a normal, legible dark-mode pattern on its own. */
    .page {{ background-color: #16160f !important; }}
    body {{ color: #f2f2ea; }}
  }}
"""


def _nb_ransom_html(winner: dict | None, pace_spread: dict | None) -> str:
    """Generalizes v59's hand-built ransom note (Charles / LECLERC / WON / even though /
    Mercedes / had the faster race pace.) across every branch _opener_html already handles,
    by semantic role rather than literal words: driver's first name -> plain (.a), surname in
    caps -> big red (.b), the verdict verb -> black box (.c), connective words -> plain (.a),
    the rival/fastest team when it differs from the winner's own team -> wavy underline (.e)."""
    raw_team = winner["constructor"] if winner and winner.get("constructor") else None
    raw_fastest = pace_spread["fastest"] if pace_spread else None
    full_name = _full_driver_name(winner["driver"]) if winner else None
    first_name, _, surname = full_name.rpartition(" ") if full_name else (None, None, None)
    first_name = html.escape(first_name) if first_name else None
    surname = html.escape(surname.upper()) if surname else None
    team = html.escape(raw_team) if raw_team else None
    fastest = html.escape(raw_fastest) if raw_fastest else None
    team_color = _team_color(raw_team) if raw_team else "#E10600"
    name_html = (
        f'<span class="a">{first_name}</span> <span class="b" style="color:{team_color}">{surname}</span>'
        if surname and first_name else
        f'<span class="b" style="color:{team_color}">{surname}</span>' if surname else None
    )

    if surname and team and fastest:
        if raw_fastest == raw_team:
            spans = (
                f'{name_html} <span class="c">WON FOR {team.upper()}</span> '
                '<span class="a">the fastest car on pace too.</span>'
            )
        else:
            spans = (
                f'{name_html} <span class="c">WON</span> '
                f'<span class="d">even though</span> <span class="e">{fastest}</span> '
                '<span class="a">had the faster race pace.</span>'
            )
    elif surname and team:
        spans = (
            f'{name_html} <span class="c">WON FOR {team.upper()}</span> '
            '<span class="a">this weekend.</span>'
        )
    elif fastest:
        spans = (
            '<span class="a">Here&rsquo;s what the telemetry found this weekend, with</span> '
            f'<span class="e">{fastest}</span> <span class="a">setting the pace.</span>'
        )
    else:
        spans = '<span class="a">Here&rsquo;s what the telemetry found this weekend.</span>'

    return f'<p class="ransom">{spans}</p>'


def _nb_practice_html(practice: dict | None) -> str:
    if practice is None:
        return ""
    tiles = []
    for sector, constructor, driver, _margin, best_time_s in practice["sectors"]:
        driver_name = _full_driver_name(driver) if driver else "Unknown"
        value = f"{best_time_s:.3f}s" if best_time_s is not None else "—"
        tiles.append((f"SECTOR {sector}", value, constructor or "Unknown", driver_name))
    kmh = practice["top_speed_kmh"]
    mph = kmh * 0.621371
    tiles.append((
        "TOP SPEED", f"{kmh:.0f} km/h",
        practice["top_speed_constructor"] or "Unknown",
        f"{_full_driver_name(practice['top_speed_driver'])} ({mph:.0f} mph)",
    ))
    # Table, not CSS grid (email.py:626 header note / project CLAUDE.md): Gmail (desktop,
    # iOS, Android, non-Workspace accounts) doesn't support display:grid, which was collapsing
    # this into one stacked column. Per-tile rotation moves onto the shadow-box's outer wrapper
    # (rotating shadow+content as one rigid unit) since it rode on :nth-child selectors that
    # don't match once tiles become <td>s.
    _tile_rotations = ["", "transform:rotate(1.5deg);margin-top:-4px;", "transform:rotate(-1.2deg);", "transform:rotate(0.8deg);margin-top:-6px;"]
    tile_divs = [
        _nb_shadow_box(
            f'<span class="lbl" style="background:{_darken(_team_color(constructor), 0.9)}">{html.escape(label)}</span>'
            f'<p class="val">{html.escape(value)}</p>'
            f'<p style="margin:0;">{html.escape(constructor)} &middot; {html.escape(driver_bit)}</p>',
            border_width="3px", offset=7, box_class="practice-tile-inner",
            box_style="padding:14px 14px 16px;",
            wrapper_style=_tile_rotations[i] if i < len(_tile_rotations) else "",
        )
        for i, (label, value, constructor, driver_bit) in enumerate(tiles)
    ]
    rows_html = "".join(
        '<tr>'
        f'<td width="50%" style="padding:0 9px 18px 0;vertical-align:top;">{tile_divs[r]}</td>'
        f'<td width="50%" style="padding:0 0 18px 9px;vertical-align:top;">{tile_divs[r + 1]}</td>'
        '</tr>'
        for r in range(0, len(tile_divs), 2)
    )
    return (
        '<span class="section-title">FAST OUT THE GATES</span>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows_html}</table>'
    )


def _nb_qualifying_html(quali: QualiInsight | None) -> str:
    if quali is None:
        return ""
    header = _clean(quali.header)
    body = _clean(_first_sentence(quali.explanation_email))
    team_color = _team_tint(quali.team, 0.18) if quali.team else _team_tint("Mercedes", 0.18)
    inner = (
        '<span class="lbl">QUALIFYING HOUR</span>'
        f'<h3>{header}</h3>'
        f'<p>{body}</p>'
    )
    return _nb_shadow_box(
        inner, bg=team_color, box_class="quali-inner",
        box_style="padding:22px 22px 26px;", wrapper_style="margin-top:44px;",
    )


def _nb_pace_spread_html(pace_spread: dict | None) -> str:
    if pace_spread is None:
        return ""
    fastest = html.escape(pace_spread["fastest"])
    pace_rows = pace_spread["rows"]
    # Table row, not display:flex (unsupported for most real Gmail recipients) -- same
    # <tr><td>label</td><td align=right>value</td></tr> idiom as render_email's own
    # _pace_spread_panel (email.py, already Gmail-safe).
    row_html = []
    for i, (name, gap) in enumerate(pace_rows):
        border = "" if i == len(pace_rows) - 1 else "border-bottom:2px dashed #0a0a0a55;"
        row_html.append(
            "<tr>"
            f'<td style="padding:10px 8px 10px 0;{border}font-size:16px;text-align:left;">'
            f'<span class="swatch" style="background:{_team_color(name)}"></span>{html.escape(name)}</td>'
            f'<td style="padding:10px 0 10px 8px;{border}text-align:right;'
            f'font-family:{_NB_DISPLAY_FONT};font-weight:700;'
            f'font-size:28px;color:{_team_color(name)};">{html.escape(gap)}</td>'
            "</tr>"
        )
    inner = (
        f'<p style="font-size:13px;margin:0 0 16px;">{fastest} set the pace this weekend. '
        f'Gap per lap, race pace:</p>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{"".join(row_html)}</table>'
    )
    return (
        '<span class="section-title">PACE SPREAD // CONSTRUCTORS</span>'
        + _nb_shadow_box(inner, box_style="padding:26px 22px 30px;", wrapper_style="margin-bottom:34px;")
    )


def _nb_next_race_html(next_race: dict | None) -> str:
    if next_race is None:
        return ""
    days = next_race["days"]
    if days == 0:
        days_stat = '<td style="padding-right:28px;"><b>TODAY</b></td>'
    elif days == 1:
        days_stat = '<td style="padding-right:28px;"><b>TOMORROW</b></td>'
    else:
        days_stat = f'<td style="padding-right:28px;"><b>{days}</b>days away</td>'
    length_km = next_race.get("length_km")
    km_stat = f'<td><b>{length_km:.3f}</b>km circuit</td>' if length_km is not None else ""
    place = (
        f'<p style="margin:0;font-size:13px;">{html.escape(next_race["place"])}</p>'
        if next_race.get("place") else ""
    )
    inner = (
        f'<span class="lbl">NEXT UP &middot; ROUND {next_race["round"]}</span>'
        f'<h3>{html.escape(next_race["name"])}</h3>{place}'
        # Table row, not display:flex+gap (unsupported for most Gmail recipients) -- was
        # collapsing "4 days away" / "4.381 km circuit" into one run-on line with no spacing.
        f'<table role="presentation" cellpadding="0" cellspacing="0" class="stats"><tr>{days_stat}{km_stat}</tr></table>'
    )
    return _nb_shadow_box(
        inner, box_class="next-race-inner", box_style="padding:24px 22px;",
        wrapper_style="margin-bottom:40px;",
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

    raw_team = winner["constructor"] if winner and winner.get("constructor") else None
    raw_fastest = pace_spread["fastest"] if pace_spread else None
    if raw_team and raw_fastest and raw_fastest != raw_team:
        verdict = "The telemetry says the fastest car didn&rsquo;t win"
    elif raw_team and raw_fastest:
        verdict = "The telemetry backs it up"
    else:
        verdict = "Here&rsquo;s what actually happened, sector by sector"
    sub = (
        f'<p class="sub">{html.escape(raw_team)} takes the {event_name}. '
        f'<b>{verdict}.</b> Here&rsquo;s what actually happened, sector by sector.</p>'
        if raw_team else
        f'<p class="sub"><b>{verdict}, sector by sector.</b></p>'
    )

    cards_html = ""
    if insights:
        cards = []
        for i, ins in enumerate(insights, start=1):
            header = _clean(ins.header)
            body = _clean(_first_sentence(ins.explanation_email))
            color = _team_color(ins.team) if ins.team else _NB_INK
            # Alternating shadow side (odd: right, even: left) echoes the comp's alternating
            # box-shadow direction (:nth-child(odd/even){box-shadow:±7px 7px}) computed here
            # instead of via CSS :nth-child, matching where the per-team border-color is
            # already computed per card.
            side = "right" if i % 2 == 1 else "left"
            badge_align = "right" if side == "right" else "left"
            # Badge renders first at its normal (known, fixed ~38px) size, corner-aligned; the
            # card box follows with a negative top margin pulling its own top edge up to tuck
            # under the badge -- same construction as the WINNER sticker above (see its
            # comment for the full reasoning on why fixed-size-first + box-pulls-up-after is
            # the bounded, predictable order, not the reverse). Real fragility in the negative
            # margin itself (Yahoo/AOL dropped support outright, Gmail's own isn't confirmed)
            # -- verify against the real send; fall back to non-overlapping badge-above-heading
            # placement if it doesn't hold.
            badge_line = f'<div style="text-align:{badge_align};margin:0 10px 0 10px;"><span class="num-flag" style="background:{color}">{i}</span></div>'
            box = _nb_shadow_box(
                f"<h3>{header}</h3><p>{body}</p>",
                border_color=color, box_class="insight-inner",
                box_style="padding:22px 20px 24px;", offset=10, side=side,
                wrapper_style="margin:-20px 0 28px;",
            )
            cards.append(badge_line + box)
        cards_html = '<span class="section-title">THE 3 INSIGHTS</span>' + "".join(cards)

    # Inline color (not the .cta class alone): Gmail's default link-blue was winning over
    # class-only anchor color in the attempt-2 send. Shadow-boxed like the panels; the anchor
    # itself is the inset content box so it stays a single click target.
    cta = _nb_shadow_box(
        f'<a href="{html.escape(cta_url)}" style="display:block;text-align:center;'
        f'font-family:{_NB_DISPLAY_FONT};font-weight:700;font-size:20px;color:#fff;'
        'text-decoration:none;padding:18px 20px;">READ THE FULL ANALYSIS</a>',
        bg="#E10600", wrapper_style="margin:20px 0 50px;",
    )

    winner_sticker = f'<div style="text-align:right;margin:0 20px 0 0;">{_nb_stamp("WINNER", bg=html.escape(_darken(_team_color(raw_team), 0.85)) if raw_team else "#E10600")}</div>'
    # Corner-overlap sticker, not position:absolute + z-index (email.py:626 header note --
    # both dead in Gmail). The sticker renders first at its normal (known, fixed-height ~40px)
    # size; the box below it pulls its own top edge up via negative margin to partially tuck
    # under the sticker -- the box paints after in DOM order, so it covers the sticker's bottom
    # slice while the sticker's top portion keeps peeking out above the box's raised edge.
    # Bounded by the sticker's fixed size rather than the box's dynamic content height, so it
    # stays predictable regardless of how long the ransom note/sub-line run. Real fragility in
    # the negative margin itself (Yahoo/AOL dropped support outright, Gmail's own support isn't
    # confirmed) -- verify against the real send; fall back to non-overlapping stacked
    # placement if it doesn't hold.
    # Top padding trimmed from 28px to 18px: the WINNER sticker already occupies visual space
    # tucked into the box's top edge (see winner_sticker's comment below), so the old 28px
    # compounded into an oversized empty gap above the ransom headline.
    headline_box = _nb_shadow_box(
        _nb_ransom_html(winner, pace_spread) + sub, box_class="headline-inner",
        box_style="padding:18px 24px 32px;", wrapper_style="margin:-22px 0 40px;",
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Telogify &mdash; {event_name}</title>
{_NB_FONTS_LINK}
<style>{_NB_STYLE}</style>
</head>
<body>
<div class="page">
<div class="sheet">

  <div class="masthead">
    {_nb_stamp(event_name)}
    <p class="wordmark">telo<span>gify</span></p>
    <div class="rip"></div>
  </div>

  {winner_sticker}
  {headline_box}

  {_nb_practice_html(practice)}
  {_nb_qualifying_html(quali_insight)}
  {_nb_pace_spread_html(pace_spread)}
  {cards_html}

  {cta}

  {_nb_next_race_html(next_race)}

  <footer>
    Methodology inputs come from Mirco Bartolozzi (@fdataanalysis), covering clean-air filtering, fuel correction, and the ERS depletion signal. Timing data comes from FastF1.<br>
    See you after the next session!<br>
    &copy; {weekend.year} Tanish Misra &middot; <a href="{html.escape(base_url.rstrip('/'))}/unsubscribe" style="color:#0a0a0a">Unsubscribe</a>
  </footer>

</div>
</div>
</body>
</html>"""


# Conversational design: near-literal port of the approved digest-v64.html comp (iMessage-style
# chat thread -- real Instrument Sans/Space Grotesk/JetBrains Mono webfonts, tight/last-in-group
# bubble grouping, a typing indicator, and v64's real two-part CTA: a decorative non-clickable
# "sent" bubble followed later by the actual clickable link). Full standalone document for the
# same reason as Neubrutalist: real webfonts need a real <head>.
#
# Gmail-safety note (see Neubrutalist's own note above for the full picture, verified via
# Context7's /hteumeuleu/caniemail): this design was worse-hit than Neubrutalist because its
# whole stylesheet was built on CSS custom properties (:root{--bg:...} + var(--bg) everywhere)
# -- Gmail keeps var() *references* but drops the :root *declaration*, so every var() silently
# resolved to nothing. All values below are literals instead. Bubble rows also relied on
# display:flex to both lay out label/value pairs (now tables) and to shrink-wrap bubbles to
# their content (now display:inline-block on the bubbles themselves, since a plain block .row
# wrapper stretches its child to full width).
_CV_FONTS_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700'
    '&family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600&display=swap" rel="stylesheet">'
)

# Short, genuinely cross-platform-identical fallback stacks (attempt 4, same reasoning as
# Neubrutalist's _NB_DISPLAY_FONT/_NB_MONO_FONT above): the previous chains (Trebuchet MS,
# -apple-system, Segoe UI...) don't all exist on every platform, so desktop and iOS were
# landing on different real fonts once the webfonts failed to load (they never do in Gmail).
# Arial/Helvetica at weight 700 (not 600 -- Arial's weight steps don't reliably resolve
# in-between cuts the same way on every engine) and Courier New alone for mono are the two
# names genuinely universal across Windows/macOS/iOS/Android.
_CV_MONO = "'JetBrains Mono', 'Courier New', Courier, monospace"
_CV_SANS = "'Space Grotesk', Arial, Helvetica, sans-serif"
_CV_DISPLAY = "'Instrument Sans', 'Space Grotesk', Arial, Helvetica, sans-serif"
_CV_INK = "#1B1612"
_CV_MUTED = "#8A837C"
_CV_SENT = "#E10600"

# No :root/var() (email.py:626 header note): Gmail keeps var() *references* but drops the
# :root declarations that define them, silently losing every color/font/spacing value this
# stylesheet routed through custom properties. Every value below is a literal instead.
_CV_STYLE = f"""
  *{{box-sizing:border-box;}}
  body{{ margin:0; }}
  .page{{ background:#EFEEE9; font-family:{_CV_SANS}; color:{_CV_INK}; padding:32px 12px 64px; }}
  .thread{{ max-width:460px; margin:0 auto; background:#FFFFFF; border-radius:20px; padding:32px 24px 28px; box-shadow:0 1px 2px rgba(27,22,18,0.04); }}
  .masthead{{ text-align:center; padding-bottom:18px; }}
  .masthead .wordmark{{ font-family:{_CV_DISPLAY}; font-size:44px; font-weight:700; color:{_CV_INK}; }}
  .masthead .wordmark span{{color:{_CV_SENT};}}
  .contact-sub{{ margin-top:6px; font-size:12px;color:{_CV_MUTED}; }}
  .day-chip{{ text-align:center; margin:18px 0 16px; }}
  .day-chip span{{ display:inline-block; background:rgba(0,0,0,0.05); color:{_CV_MUTED}; font-size:11px; font-weight:600; padding:4px 12px; border-radius:20px; letter-spacing:0.02em; }}
  .row{{ margin-bottom:8px; }}
  .row.tight{{margin-bottom:3px;}}
  .bubble{{ display:inline-block; background:#FFFFFF; border:1px solid #D4D1C6; border-radius:19px; border-bottom-left-radius:5px; padding:11px 15px; max-width:84%; font-size:15.5px; line-height:1.42; box-shadow:0 1px 1px rgba(27,22,18,0.03); }}
  .row.tight .bubble{{border-bottom-left-radius:19px;}}
  .row.last-in-group .bubble{{border-bottom-left-radius:5px;}}
  strong{{font-weight:700;}}
  .num{{ font-family:{_CV_MONO}; font-weight:600; color:{_CV_SENT}; }}
  .team-label{{ font-weight:700; }}
  .data-bubble{{ display:inline-block; background:#FFFFFF; border:1px solid #D4D1C6; border-radius:19px; border-bottom-left-radius:5px; padding:10px 16px; max-width:97%; }}
  .data-label{{color:{_CV_INK};}}
  .data-label .sub{{color:{_CV_MUTED};font-size:13.5px;display:block;margin-top:1px;}}
  .data-val{{ font-family:{_CV_MONO}; font-weight:600; font-size:17px; color:{_CV_INK}; white-space:nowrap; padding-left:12px; }}
  .insight-bubble{{ display:inline-block; background:#FFFFFF; border:1px solid #D4D1C6; border-radius:19px; border-bottom-left-radius:5px; padding:16px 18px; max-width:97%; }}
  .insight-tag{{ display:inline-block; font-family:{_CV_MONO}; font-size:10.5px; font-weight:600; letter-spacing:0.06em; text-transform:uppercase; background:transparent; padding:2px 8px; border-radius:5px; border-width:1.5px; border-style:solid; margin-bottom:8px; }}
  .insight-head{{ font-weight:700; font-size:17px; line-height:1.32; margin:0 0 5px; }}
  .insight-body{{ font-size:15px; line-height:1.48; color:#4A443E; margin:0; }}
  .typing{{ display:inline-block; background:#FFFFFF; border:1px solid #D4D1C6; border-radius:19px; border-bottom-left-radius:5px; padding:13px 16px; }}
  .typing i{{ width:6px;height:6px;border-radius:50%; background:#C9C4BC; display:inline-block; margin-right:4px; }}
  .typing i:last-child{{margin-right:0;}}
  .timestamp{{ text-align:center; font-size:11px; color:{_CV_MUTED}; margin:14px 0 6px; }}
  .sent-row{{ text-align:right; margin:18px 0 8px; }}
  .sent-bubble{{ display:inline-block; background:{_CV_SENT}; color:#FFF6F5; border-radius:19px; border-bottom-right-radius:5px; padding:11px 16px; max-width:78%; font-size:15px; font-weight:600; }}
  .quick-replies{{ margin-top:14px; padding-left:2px; }}
  .qr{{ display:inline-block; text-decoration:none; font-family:{_CV_SANS}; font-size:14px; font-weight:700; color:#FFF6F5; background:{_CV_SENT}; padding:11px 18px; border-radius:20px; margin:0 8px 8px 0; }}
  .meta-footer{{ margin-top:30px; font-size:11.5px; color:{_CV_MUTED}; line-height:1.7; }}
  .meta-footer a{{color:{_CV_MUTED};}}
  @media screen and (min-width: 600px) {{
    /* Desktop reads as a real desktop layout instead of a stretched phone screen: wider
       thread column, the border back (removed by default above so mobile isn't boxed in),
       and a font-size step up across the main bubble text. Standard responsive-email layout
       media query -- a different, well-supported mechanism from the dark-mode one below;
       layout media queries work fine in Gmail (unlike prefers-color-scheme on its apps). */
    .thread {{ max-width: 640px; border: 1px solid #D4D1C6; padding: 40px 40px 36px; }}
    .masthead .wordmark {{ font-size: 50px; }}
    .bubble {{ font-size: 17px; }}
    .data-val {{ font-size: 19px; }}
    .data-label .sub {{ font-size: 15px; }}
    .insight-head {{ font-size: 19px; }}
    .insight-body {{ font-size: 16.5px; }}
  }}
  @media (prefers-color-scheme: dark) {{
    /* Best-effort only (email.py:626 header note): Gmail's iOS/Android apps -- where the
       worst dark-mode reports came from, including red reading as orange -- ignore this media
       query entirely and run their own automatic color inversion instead, which nothing here
       can override. This helps the clients that DO respect it (Apple Mail, Samsung Email,
       Gmail desktop webmail): keeps the real brand red instead of letting an auto-inversion
       algorithm guess at it. */
    .page {{ background-color: #18181a !important; }}
    .thread {{ background-color: #232326 !important; border-color: #38383c !important; }}
    body {{ color: #EFEEE9; }}
  }}
"""


def _cv_row(content_html: str, row_class: str = "", *, team: str | None = None) -> str:
    cls = f"row {row_class}" if row_class else "row"
    if team:
        border = _darken(_team_color(team), 0.75)
        bg = _team_color_alpha(team, 0.12)
        style = f' style="border-color:{border};background:{bg}"'
    else:
        style = ""
    return f'<div class="{cls}"><div class="bubble"{style}>{content_html}</div></div>'


def _cv_stat_bubble(row_html: str, team: str | None, row_class: str = "") -> str:
    """A single-stat data-bubble (one practice sector, or one team's race-pace gap) sent as its
    own chat message: a light team-color wash and a dark team-color border replace the neutral
    bubble palette, so identity lives on the bubble itself now that each stat is its own text
    rather than one row inside a shared table."""
    cls = f"row {row_class}" if row_class else "row"
    if team:
        border = _darken(_team_color(team), 0.75)
        bg = _team_color_alpha(team, 0.12)
        style = f' style="border-color:{border};background:{bg}"'
    else:
        style = ""
    return f'<div class="{cls}"><div class="data-bubble"{style}>{row_html}</div></div>'


def _cv_data_row(label_html: str, value: str, *, value_color: str | None = None) -> str:
    # Table row, not display:flex (unsupported for most real Gmail recipients) -- was
    # collapsing label/value onto one run-on line with no spacing. Each call is the sole row
    # inside its own stat bubble (see _cv_stat_bubble callers), so no border/last-child needed.
    # No width="100%": the bubble already shrink-wraps to content (display:inline-block), so a
    # forced-full-width table only risks stretching it in less careful renderers; the label/
    # value gap comes from .data-val's own padding-left. vertical-align:top/baseline instead of
    # the table default (middle), which was center-aligning a two-line label (name + sub-line)
    # against the value -- the old flex row used align-items:baseline.
    color_style = f"color:{value_color};" if value_color else ""
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0"><tr>'
        f'<td class="data-label" style="vertical-align:top">{label_html}</td>'
        f'<td class="data-val num" style="text-align:right;vertical-align:baseline;{color_style}">{html.escape(value)}</td>'
        '</tr></table>'
    )


def _cv_emphasize_numbers(escaped_text: str) -> str:
    return _NUM_RE.sub(lambda m: f'<span class="num">{m.group(0)}</span>', escaped_text)


def _cv_insight_bubble(tag_text: str | None, team: str | None, header: str, body: str) -> str:
    # a raw light team color (e.g. McLaren orange, Mercedes teal) reads too faint at that
    # weight, so darken it the same way _darken already does for pace-row gap numbers. Border
    # color is set inline explicitly (not CSS currentColor) since it's the one property most
    # likely to get lost to a client's own default if left to inherit.
    color = _darken(_team_color(team), 0.5) if team else _MUTED
    tag = f'<span class="insight-tag" style="color:{color};border-color:{color}">{html.escape(tag_text)}</span>' if tag_text else ""
    return (
        '<div class="row"><div class="insight-bubble">'
        f'{tag}'
        f'<p class="insight-head">{header}</p><p class="insight-body">{body}</p>'
        '</div></div>'
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

    driver = _full_driver_name(winner["driver"]) if winner else None
    team = winner["constructor"] if winner and winner.get("constructor") else None

    bubbles = [_cv_row("Hey, the race is done! Results are in.", "tight")]
    if driver and team:
        bubbles.append(_cv_row(f"<strong>{html.escape(driver)} won it for {html.escape(team)}.</strong>", "last-in-group"))
    else:
        bubbles.append(_cv_row(preheader_text, "last-in-group"))

    if practice is not None:
        bubbles.append(_cv_row("First up, practice:", "tight"))

        def _practice_bubble(tag: str, constructor: str | None, driver: str | None, value: str, row_class: str) -> str:
            driver_bit = f" ({html.escape(_full_driver_name(driver))})" if driver else ""
            if constructor:
                darkened = _darken(_team_color(constructor), 0.75)
                sub = f'<span class="sub"><span style="color:{darkened}">{html.escape(constructor)}</span>{driver_bit}</span>'
                row = _cv_data_row(f"{tag}{sub}", value, value_color=darkened)
                return _cv_stat_bubble(row, constructor, row_class)
            sub = f'<span class="sub">Unknown{driver_bit}</span>'
            row = _cv_data_row(f"{tag}{sub}", value)
            return _cv_stat_bubble(row, None, row_class)

        kmh = practice["top_speed_kmh"]
        stats = [
            (f"Sector {sector}", constructor, drv, f"{best_time_s:.3f}s" if best_time_s is not None else "—")
            for sector, constructor, drv, _margin, best_time_s in practice["sectors"]
        ]
        stats.append(("Top speed", practice["top_speed_constructor"], practice["top_speed_driver"], f"{kmh:.0f} km/h"))
        for i, (tag, constructor, drv, value) in enumerate(stats):
            row_class = "tight" if i < len(stats) - 1 else "last-in-group"
            bubbles.append(_practice_bubble(tag, constructor, drv, value, row_class))

    if quali_insight is not None:
        header = _clean(quali_insight.header)
        body = _cv_emphasize_numbers(_clean(_first_sentence(quali_insight.explanation_email)))
        bubbles.append(_cv_row(f"And from qualifying, one thing stood out: <strong>{header}</strong>", "tight"))
        bubbles.append(_cv_row(body, "last-in-group"))

    if pace_spread is not None:
        bubbles.append(
            '<div class="timestamp">Telogify is typing&hellip;</div>'
            '<div class="row"><div class="typing"><i></i><i></i><i></i></div></div>'
        )
        fastest_raw = pace_spread["fastest"]
        fastest = html.escape(fastest_raw)
        pace_rows = pace_spread["rows"]
        n = len(pace_rows)
        number_word = {1: "one", 2: "two", 3: "three"}.get(n, str(n))
        team_word = "team" if n == 1 else "teams"
        bubbles.append(_cv_row("Onto the race.", "tight"))
        fastest_color = _darken(_team_color(fastest_raw), 0.75)
        bubbles.append(_cv_row(
            f'<strong style="color:{fastest_color}">{fastest}</strong> actually had the pace edge.',
            "tight", team=fastest_raw,
        ))
        bubbles.append(_cv_row(f"Here&rsquo;s the gap to the other {number_word} {team_word}:", "tight"))
        for i, (name, gap) in enumerate(pace_rows):
            darkened = _darken(_team_color(name), 0.75)
            short = html.escape(_team_short_name(name))
            row = _cv_data_row(f'<span class="team-label" style="color:{darkened}">{short}</span>', gap, value_color=darkened)
            row_class = "tight" if i < len(pace_rows) - 1 else "last-in-group"
            bubbles.append(_cv_stat_bubble(row, name, row_class))
        bubbles.append(_cv_row(f"(And by the way, those are gaps to {fastest}, per lap.)", "last-in-group"))

    if insights:
        surname = driver.split()[-1] if driver else None
        intro = f"{html.escape(surname)} won on something else. Here are the three things worth knowing from the race itself." if surname else "Here are the three things worth knowing from the race itself."
        bubbles.append(_cv_row(intro, "tight"))
        for i, ins in enumerate(insights, start=1):
            header = _clean(ins.header)
            body = _cv_emphasize_numbers(_clean(_first_sentence(ins.explanation_email)))
            bubbles.append(_cv_insight_bubble(f"0{i}", ins.team, header, body))

    bubbles.append(_cv_row("That&rsquo;s the recap!", "tight"))
    bubbles.append('<div class="sent-row"><div class="sent-bubble">I want to read the full analysis!</div></div>')
    bubbles.append(_cv_row("Yesss, love that!", "last-in-group"))

    if next_race is not None:
        days = next_race["days"]
        when = "today" if days == 0 else ("tomorrow" if days == 1 else f"{days} days")
        length_km = next_race.get("length_km")
        length_bit = f" on a {length_km:.3f} km circuit" if length_km is not None else ""
        place_bit = f" in {html.escape(next_race['place'])}" if next_race.get("place") else ""
        bubbles.append(
            '<div class="row"><div class="insight-bubble" style="max-width:88%">'
            f'<p class="insight-body">Next up: the {html.escape(next_race["name"])}{place_bit}, '
            f'{when} away{length_bit}.</p></div></div>'
        )

    # Solid-fill button, not outlined/tinted (attempt-3 version tested as too visually thin
    # to register as a real button next to the bold .sent-bubble right above it, and read as
    # "maybe broken"). Inline color (not the .qr class alone): Gmail's default link-blue was
    # winning over class-only anchor color in the attempt-2 send.
    bubbles.append(
        f'<div class="quick-replies"><a class="qr" href="{html.escape(cta_url)}" '
        f'style="color:#FFF6F5;background:{_CV_SENT}">Read the full analysis &rarr;</a></div>'
    )
    bubbles.append('<div class="row tight" style="margin-top:14px"><div class="bubble">See you after the next session!</div></div>')

    footer = (
        'Methodology inputs come from Mirco Bartolozzi (@fdataanalysis), covering clean-air filtering, '
        'fuel correction, and the ERS depletion signal. Timing data comes from FastF1.<br><br>'
        f"&copy; {weekend.year} Tanish Misra &middot; "
        f'<a href="{html.escape(base_url.rstrip("/"))}/unsubscribe" style="color:{_CV_MUTED}">Unsubscribe</a>'
    )

    day_chip = f'<div class="day-chip"><span>{now.strftime("%A").upper()}</span></div>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Telogify &mdash; {event_name} recap</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
{_CV_FONTS_LINK}
<style>{_CV_STYLE}</style>
</head>
<body>
<div class="page">
<div class="thread">

  <div class="masthead">
    <span class="wordmark">Telo<span>gify</span></span>
    <div class="contact-sub">{event_name}</div>
  </div>

  {day_chip}

  {"".join(bubbles)}

  <div class="meta-footer">{footer}</div>

</div>
</div>
</body>
</html>"""


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
