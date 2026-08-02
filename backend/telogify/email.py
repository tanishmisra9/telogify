"""Post-race email digest via Resend.

`render_email_neubrutalist` is the sole digest design (pure, testable): a big centered
masthead, a one-line opener naming the winner, a Practice section ("Fast out the gates":
sector dominance + top speed), a Qualifying section (one quali car-character insight), the 3
race insight cards, a Constructors pace-spread panel (real per-constructor race-pace gaps, the
same canonical median metric as the /pace chart and constructor ranking), a CTA, a next-race
panel, and a footer with methodology credit and copyright/unsubscribe. No em dashes.
`render_email_plaintext` is its plain-text sibling for the multipart/alternative text part.
`send_digest` sends one message per subscriber (both parts) so addresses are never shared
across recipients.
"""

import html
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
from telogify.serialize import format_lap_times, strip_em_dashes

# Same practice/sprint-quali session set the site's own /sectors and /topspeeds endpoints treat
# as "indicative" (api/routes.py's INDICATIVE_SESSIONS) -- conditions vary run to run, so these
# are read as a snapshot, not a qualifying-grade ranking.
_INDICATIVE_SESSIONS = ("FP1", "FP2", "FP3", "SQ")

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


_MUTED = "#605954"

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


def _relative_luminance(hex_color: str) -> float:
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def _on_color(hex_color: str) -> str:
    """Text/icon color for a solid fill of hex_color: ink on light fills (papaya, teal,
    silver), white on dark fills (Ferrari red, navy) -- so a solid chip never has to be
    darkened away from the real team color just to keep its own label legible."""
    return _NB_INK if _relative_luminance(hex_color) > 0.5 else "#fff"


def _clean(text: str) -> str:
    # format_lap_times at render, not on persist: it fixes the already-persisted insights too,
    # which a persist-time hook could only do by re-running the paid pipeline.
    return html.escape(format_lap_times(strip_em_dashes(text)) or "")


def _first_sentence(text: str) -> str:
    """Safety net: the prompt asks the agent for exactly one sentence; this guarantees it
    even if a generation slips, without touching explanation_web."""
    parts = _SENTENCE_SPLIT_RE.split(text.strip())
    return parts[0] if parts else text


def _opener_html(winner: dict | None, pace_spread: dict | None = None) -> str:
    """Stays generic about the weekend (no event name) since the kicker above it already names
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
    return text


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
    """Plain-text sibling of render_email_neubrutalist for the multipart/alternative text part
    sending infrastructure (and some spam filters) expect alongside the HTML. Real driver/team/
    circuit names never contain HTML-special characters, so reusing _opener_html's already-
    "escaped" opener text here is safe -- html.escape is a no-op on this domain's inputs."""
    cta_url = f"{base_url.rstrip('/')}/weekends/{weekend.year}/{weekend.round}"
    opener_text = _opener_html(winner, pace_spread)

    lines = [f"TELOGIFY · {weekend.event_name}", "", opener_text, ""]

    if practice is not None:
        lines.append("FAST OUT THE GATES IN PRACTICE")
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
        header = format_lap_times(strip_em_dashes(quali_insight.header)) or ""
        body = format_lap_times(strip_em_dashes(_first_sentence(quali_insight.explanation_email))) or ""
        lines.append(header)
        lines.append(body)
        lines.append("")

    lines.append("HERE'S YOUR THREE INSIGHTS")
    lines.append("")
    for i, ins in enumerate(insights, start=1):
        header = format_lap_times(strip_em_dashes(ins.header)) or ""
        body = format_lap_times(strip_em_dashes(_first_sentence(ins.explanation_email))) or ""
        lines.append(f"{i:02d}. {header}")
        lines.append(body)
        lines.append("")

    if pace_spread is not None:
        lines.append("SUNDAY'S FRONT RUNNERS")
        lines.append(
            f"{pace_spread['fastest']} set the pace this weekend. Here's how much time the "
            "next three lost, every single lap."
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


# Shared by both full-document designs' <head> (attempt 5, dark-mode best effort): declares
# real support for both color schemes so clients that DO respect this signal (Apple Mail,
# Outlook.com) use our own @media (prefers-color-scheme:dark) rules instead of guessing via
# their own inversion heuristic. Doesn't help Gmail's iOS/Android apps -- verified (Context7's
# /hteumeuleu/caniemail plus multiple 2026 sources) that they ignore this meta tag entirely and
# run their own automatic full inversion regardless. See the real fix plan in
# .claude/plans/gmail-dark-mode-real-fix.md for what it would actually take to control that.
_META_COLOR_SCHEME = (
    '<meta name="color-scheme" content="light dark">'
    '<meta name="supported-color-schemes" content="light dark">'
)

# Neubrutalist design: near-literal port of the approved digest-v59.html comp (punk-zine
# collage -- torn strip, rotated stickers/tiles/cards, ransom-note headline, alternating
# insight-card shadows via real :nth-child, real Archivo Black/Space Mono webfonts). Returns a
# full standalone HTML document (doctype/head/style), not a body fragment -- real webfonts and
# a dot-pattern canvas need a real <head>.
#
# Real send test (Resend -> real Gmail address) found Gmail (desktop webmail + iOS/Android,
# the overwhelming majority of recipients) strips or ignores: transform (no rotation, any
# platform), the left/right/top/bottom offsets a position:absolute element needs to actually
# be positioned, display:flex/grid, box-shadow (desktop webmail), inline <svg>, and CSS custom
# properties (var() references survive, :root declarations don't -- N/A here, Neubrutalist
# never used them). Verified against Context7's /hteumeuleu/caniemail. Grid/flex rows, the
# WINNER sticker, and the insight number badges are now table-based / normal-flow instead of
# relying on those properties; transform/box-shadow/clip-path stay in the stylesheet since
# Gmail ignores them for free and Apple Mail/Samsung Email/Thunderbird still render the fuller
# collage effect.
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
    bg: str = "#FEFEFE",
    border_color: str = _NB_INK,
    border_width: str = "3px",
    shadow_color: str = _NB_INK,
    offset: float = 7,
    side: str = "right",
    inline: bool = False,
    box_class: str = "",
    box_style: str = "",
    wrapper_style: str = "",
) -> str:
    """Real CSS box-shadow -- confirmed supported on Gmail iOS by emailsim's measured CSS
    support matrix (backend/telogify/emailsim/support.py), which is why this is no longer the
    two-nested-div fake it used to be (that trick existed only because box-shadow was believed
    unsupported everywhere; it wasn't, at least not on the client that matters most). One div,
    a real border, a real offset shadow -- the same technique the approved comp
    (digest-neubrutalist.html) uses directly. `side` flips which way the shadow's horizontal
    offset points, for the insight cards' alternating motif; `wrapper_style` carries the box's
    own margin/transform (kept as a separate param from `box_style`'s inner padding only because
    every call site already writes it that way, not because they land on different elements
    anymore -- both concatenate onto this same div)."""
    display = "inline-block" if inline else "block"
    dx = offset if side == "right" else -offset
    cls = f' class="{box_class}"' if box_class else ""
    return (
        f'<div{cls} style="display:{display};background:{bg};'
        f"border:{border_width} solid {border_color};"
        f"box-shadow:{dx}px {offset}px 0 0 {shadow_color};"
        f'{wrapper_style}{box_style}">'
        f"{inner_html}</div>"
    )


def _nb_stamp(text_html: str, *, bg: str = "#E10600", fg: str | None = None, inline: bool = True, rotate: float = -4) -> str:
    # rotate=-4 matches the comp's .stamp class exactly (used for both the masthead event-name
    # stamp and the WINNER sticker there) -- transform:rotate is confirmed supported.
    return _nb_shadow_box(
        text_html, bg=bg, border_width="1.5px", offset=3, inline=inline,
        box_style=(
            f"color:{fg or _on_color(bg)};font-family:{_NB_DISPLAY_FONT};font-weight:700;"
            "padding:10px 18px;font-size:15px;letter-spacing:0.02em;"
        ),
        wrapper_style=f"transform:rotate({rotate}deg);" if rotate else "",
    )


def _nb_logo_chip(base_url: str) -> str:
    """The masthead icon (comp's .logo-mark): a real hosted <img>, not an inline <svg> element
    -- the comp's inline SVG geometry is coincidentally identical to the site's own real mark
    (frontend/public/favicon.svg, frontend/src/components/Logo.tsx), already live at
    {base_url}/favicon.svg. Referencing an external image via <img src> is an entirely
    different, far more standard code path than embedding raw <svg> markup in the email body
    (this is how essentially every marketing email includes a logo); unlike inline SVG, this
    isn't a technique this project's own probes have ever found reason to distrust."""
    logo_url = f"{base_url.rstrip('/')}/favicon.svg"
    return _nb_shadow_box(
        f'<img src="{html.escape(logo_url)}" width="24" height="24" alt="" style="display:block;width:24px;height:24px;">',
        bg="#fff", border_width="3px", offset=4, inline=True,
        box_style="padding:6px;", wrapper_style="transform:rotate(-6deg);",
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
  /* padding-bottom used to reserve room for the torn-strip underline; that's gone, so it was
     pure dead space stacking on top of margin-bottom (86px total) and holding the reader off
     the content. */
  .masthead {{ text-align: center; margin-bottom: 30px; }}
  .masthead .wordmark {{ font-family: {_NB_DISPLAY_FONT}; font-weight: 700; font-size: 52px; line-height: 0.9; margin: 18px 0 0; letter-spacing: -0.01em; }}
  .masthead .wordmark span {{ color: #E10600; }}
  /* attempt 6: one uniform size on the headline line (name + verdict), not the old mixed
     22/44/30/38px inline run -- that's what let it baseline-align by construction instead of
     wrapping into uneven gaps. */
  .headline {{ font-family: {_NB_DISPLAY_FONT}; font-weight: 700; font-size: 28px; line-height: 1.3; margin: 0; }}
  /* attempt 7 item 2: moved off black -- brand red instead, the same fill already proven
     legible white-on-red in both light and dark mode (masthead stamp, CTA), so no new
     dark-mode override is needed here either. */
  .headline .verdict {{ background: #E10600; color: #fff; padding: 2px 8px; display: inline-block; }}
  .sub {{ font-size: 14px; line-height: 1.6; margin-top: 14px; max-width: 56ch; }}
  .sub b {{ background: #FFE500; padding: 0 3px; }}
  .section-title {{ font-family: {_NB_DISPLAY_FONT}; font-weight: 700; font-size: 22px; display: inline-block; background: #0a0a0a; color: #fff; padding: 6px 14px; margin: 0 0 18px; transform: rotate(1.5deg); }}
  .swatch {{ display:inline-block; width:14px; height:14px; margin-right:8px; border:1px solid #0a0a0a; vertical-align:middle; }}
  .practice-tile-inner {{ font-size: 13px; }}
  .practice-tile-inner .lbl {{ font-family: {_NB_DISPLAY_FONT}; font-weight: 700; font-size: 11px; background: #FFE500; color: #fff; display: inline-block; padding: 1px 6px; margin-bottom: 6px; }}
  .practice-tile-inner .val {{ font-family: {_NB_DISPLAY_FONT}; font-weight: 700; font-size: 20px; margin: 2px 0; }}
  .quali-inner .lbl {{ font-family: {_NB_DISPLAY_FONT}; font-weight: 700; font-size: 12px; background: #0a0a0a; color: #fff; display: inline-block; padding: 3px 10px; transform: rotate(-2deg); }}
  .quali-inner h3 {{ font-family: {_NB_DISPLAY_FONT}; font-weight: 700; font-size: 21px; margin: 12px 0 8px; line-height: 1.15; }}
  .quali-inner p {{ font-size: 14px; line-height: 1.6; margin: 0; max-width: 54ch; }}
  .insight-inner h3 {{ font-family: {_NB_DISPLAY_FONT}; font-weight: 700; font-size: 19px; margin: 0 0 8px; line-height: 1.2; }}
  .insight-inner p {{ font-size: 14px; line-height: 1.65; margin: 0; }}
  .nb-num {{ display: inline-block; font-family: {_NB_DISPLAY_FONT}; font-weight: 700; font-size: 12px; letter-spacing: 0.04em; padding: 4px 9px; border-radius: 3px; margin-bottom: 10px; }}
  .next-race-inner h3 {{ font-family: {_NB_DISPLAY_FONT}; font-weight: 700; font-size:24px; margin:12px 0 6px; }}
  .next-race-inner .lbl {{ font-family: {_NB_DISPLAY_FONT}; font-weight: 700; font-size:11px; color:#fff; background:#E10600; padding:3px 9px; display:inline-block; transform: rotate(-2deg); }}
  .next-race-inner .stats {{ margin-top:14px; font-size:13px; }}
  /* item 7: label sits to the right of the number, baseline-aligned ("27 days away" as one
     phrase), not stacked below it -- the old display:block on b pushed the label onto its own
     line under the figure. */
  .next-race-inner .stats b {{ font-family: {_NB_DISPLAY_FONT}; font-weight: 700; font-size:22px; color:#E10600; margin-right:6px; }}
  .next-race-inner .stats .stat-label {{ font-size:13px; color:#0a0a0a; }}
  /* A genuine sign-off, not a line buried in the small-print footer: same display font as the
     section headings so it reads as the last beat of the email's own voice, not legal copy.
     Left-justified per item 5, matching the rest of the email's left-aligned prose. */
  .closer {{ font-family: {_NB_DISPLAY_FONT}; font-weight: 700; font-size: 19px; text-align: left; margin: 32px 0 40px; color: #0a0a0a; }}
  footer {{ font-size: 12px; line-height: 1.8; color: #0a0a0a99; border-top: 1.5px solid #0a0a0a; padding-top: 18px; }}
  @media (prefers-color-scheme: dark) {{
    /* Best-effort only (email.py:626 header note, .claude/plans/gmail-dark-mode-real-fix.md
       for the real fix): Gmail's iOS/Android apps -- where the worst dark-mode reports came
       from -- ignore this media query outright and run their own automatic color inversion
       instead, which nothing here can override. This helps the clients that DO respect it
       (Apple Mail, Samsung Email, Gmail desktop webmail): real dark panels with the brand red/
       team colors preserved as-is, instead of Gmail's own guess. !important is required since
       _nb_shadow_box sets panel background/border inline per-instance (higher specificity
       than any stylesheet rule without it). Solid-fill colorful elements (stamps, the
       qualifying block's team tint) are deliberately left alone -- they're already
       high-contrast against both light and dark, and forcing them to a generic dark panel
       would erase the team-color identity that's the point of showing them in the first
       place. */
    /* .page sets its own color:#0a0a0a outside this block, which (being an explicit
       declaration, not inherited) otherwise wins over body's dark-mode color regardless of
       @media -- override it directly rather than relying on inheritance from body. */
    .page {{ background-color: #16160f !important; color: #f2f2ea; }}
    body {{ color: #f2f2ea; }}
    .sheet {{ background-color: #1e1e18 !important; border-color: #3a3a30 !important; }}
    .headline-inner, .flat-panel-inner, .practice-tile-inner, .next-race-inner {{
      background-color: #29291f !important; border-color: #f2f2ea !important; color: #f2f2ea;
    }}
    .insight-inner {{ background-color: #29291f !important; color: #f2f2ea; }}
    /* The CTA is an outlined box now, not a solid red fill, so unlike the stamps it can't be
       left alone here: its off-white background would sit on the dark page as a glaring white
       slab. Dark panel instead, with the brand red brightened for both border and label --
       #E10600 straight onto #29291f only reaches ~2.9:1, under the 3:1 large-text floor. */
    .cta-inner {{ background-color: #29291f !important; border-color: #ff6b5e !important; }}
    .cta-inner a {{ color: #ff6b5e !important; }}
    /* Same brand-red-on-dark contrast problem as the CTA above, caught the same way (real
       browser dark-mode screenshot, not a hypothetical): #E10600 straight onto a dark panel or
       the dark page/sheet background computes to roughly 1.2-1.5:1, nowhere near the 3:1 large-
       text floor -- brand red is simply too dark a red to read on its own against anything this
       dark. Same brightened red used everywhere else red needs to sit directly on a dark
       background in this block. */
    .next-race-inner .stats b {{ color: #ff6b5e !important; }}
    .masthead .wordmark span {{ color: #ff6b5e; }}
    /* The pace-spread gap figure ("+0.238s") sets color:#0a0a0a inline (email.py's own ink
       constant, chosen so it never drifted per-team like the old darkened-team-color version
       did) -- an inline declaration, so it wins over .flat-panel-inner's inherited light text
       regardless of @media without !important here. Same real-browser-screenshot catch as the
       next-race stats above: ink-on-ink was unreadable. */
    .flat-panel-inner td {{ color: #f2f2ea !important; }}
    /* quali-inner's background stays the light team tint (deliberately unchanged, see the
       comment on the media block's opening) -- but its own text and heading have no color of
       their own in the base stylesheet, so without this reset they'd inherit .page's new
       light dark-mode color while sitting on an unchanged light background. Real bug caught
       in the real-browser dark-mode screenshot check, not a hypothetical. */
    .quali-inner {{ color: #0a0a0a; }}
    .sub, .insight-inner p {{ color: #d8d8c8; }}
    .sub b {{ color: #0a0a0a; }}
    .closer {{ color: #f2f2ea; }}
    footer {{ color: #a8a89c; border-top-color: #3a3a30; }}
    footer a {{ color: #d8d8c8 !important; }}
  }}
"""


def _nb_headline_html(winner: dict | None) -> str:
    """attempt 6: replaces the old ransom note (four inline font sizes, one of them a padded
    black box -- can never baseline-align in Gmail-safe CSS, which read as scattered fragments).
    Now a single line at one uniform size: the driver's full name in the team's real color,
    immediately followed by the verdict in a black box. Hierarchy comes from color and the box,
    not from mixing sizes, so the line aligns and wraps evenly by construction."""
    raw_team = winner["constructor"] if winner and winner.get("constructor") else None
    full_name = _full_driver_name(winner["driver"]) if winner else None
    name = html.escape(full_name.upper()) if full_name else None
    team = html.escape(raw_team) if raw_team else None
    team_color = _team_color(raw_team) if raw_team else "#E10600"

    if name and team:
        spans = (
            f'<span class="name" style="color:{team_color}">{name}</span> '
            f'<span class="verdict">WON FOR {team.upper()}</span>'
        )
    else:
        spans = '<span class="verdict">HERE&rsquo;S WHAT THE TELEMETRY FOUND</span>'

    return f'<p class="headline">{spans}</p>'


def _nb_sub_html(winner: dict | None, pace_spread: dict | None) -> str:
    """attempt 6 item 9: drops ', sector by sector.' and always ends on 'happened!'; the
    winner-vs-fastest-car fact still leads, highlighted, but never repeats the headline's own
    words back."""
    raw_team = winner["constructor"] if winner and winner.get("constructor") else None
    raw_fastest = pace_spread["fastest"] if pace_spread else None
    if raw_team and raw_fastest:
        if raw_fastest == raw_team:
            lead = "The fastest car on pace too."
        else:
            lead = f"Though {html.escape(raw_fastest)} had the faster race pace."
        return f'<p class="sub"><b>{lead}</b> Here&rsquo;s what actually happened!</p>'
    return '<p class="sub"><b>Here&rsquo;s what actually happened!</b></p>'


def _nb_practice_html(practice: dict | None) -> str:
    if practice is None:
        return ""
    tiles = []
    for sector, constructor, driver, _margin, best_time_s in practice["sectors"]:
        driver_name = _full_driver_name(driver) if driver else "Unknown"
        value = f"{best_time_s:.3f}s" if best_time_s is not None else "—"
        tiles.append((f"SECTOR {sector}", value, constructor or "Unknown", driver_name, ""))
    kmh = practice["top_speed_kmh"]
    mph = kmh * 0.621371
    tiles.append((
        "TOP SPEED", f"{kmh:.0f} km/h",
        practice["top_speed_constructor"] or "Unknown",
        f"{_full_driver_name(practice['top_speed_driver'])}",
        # attempt 6 item 10: mph moves onto the value line (with the km/h figure it belongs
        # to) instead of tacking onto the driver name, which read as part of the driver's name.
        f' <span style="font-size:13px;font-weight:400;color:{_MUTED}">({mph:.0f} mph)</span>',
    ))
    # Table, not CSS grid (email.py:626 header note / project CLAUDE.md): Gmail (desktop,
    # iOS, Android, non-Workspace accounts) doesn't support display:grid, which was collapsing
    # this into one stacked column. Per-tile rotation moves onto the shadow-box's outer wrapper
    # (rotating shadow+content as one rigid unit) since it rode on :nth-child selectors that
    # don't match once tiles become <td>s.
    _tile_rotations = ["", "transform:rotate(1.5deg);margin-top:-4px;", "transform:rotate(-1.2deg);", "transform:rotate(0.8deg);margin-top:-6px;"]
    tile_divs = [
        _nb_shadow_box(
            f'<span class="lbl" style="background:{_team_color(constructor)};color:{_on_color(_team_color(constructor))}">{html.escape(label)}</span>'
            f'<p class="val">{html.escape(value)}{mph_html}</p>'
            f'<p style="margin:0;">{html.escape(constructor)} &middot; {html.escape(driver_bit)}</p>',
            border_width="1.5px", offset=3.5, box_class="practice-tile-inner",
            box_style="padding:14px 14px 16px;",
            wrapper_style=_tile_rotations[i] if i < len(_tile_rotations) else "",
        )
        for i, (label, value, constructor, driver_bit, mph_html) in enumerate(tiles)
    ]
    rows_html = "".join(
        '<tr>'
        f'<td width="50%" style="padding:0 9px 18px 0;vertical-align:top;">{tile_divs[r]}</td>'
        f'<td width="50%" style="padding:0 0 18px 9px;vertical-align:top;">{tile_divs[r + 1]}</td>'
        '</tr>'
        for r in range(0, len(tile_divs), 2)
    )
    return (
        '<span class="section-title">FAST OUT THE GATES IN PRACTICE</span>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows_html}</table>'
    )


def _nb_qualifying_html(quali: QualiInsight | None) -> str:
    if quali is None:
        return ""
    header = _clean(quali.header)
    body = _clean(_first_sentence(quali.explanation_email))
    team = quali.team or "Mercedes"
    team_color = _team_tint(team, 0.18)
    # attempt 6 item 1: the team name used to be recolored via a flat _darken(0.75), which
    # turned McLaren papaya into brown. Team identity now lives in the panel's own background
    # tint (already this team's real color) and the QUALIFYING HOUR label's solid fill below,
    # so the inline prose stays plain ink instead of duplicating (and muddying) the color cue.
    lbl_color = _team_color(team)
    inner = (
        f'<span class="lbl" style="background:{lbl_color};color:{_on_color(lbl_color)}">QUALIFYING HOUR</span>'
        f'<h3>{header}</h3>'
        f'<p>{body}</p>'
    )
    return _nb_shadow_box(
        inner, bg=team_color, box_class="quali-inner",
        # margin-bottom matches headline_box's own 40px, so the section-title after this panel
        # (PACE SPREAD // CONSTRUCTORS) gets the same breathing room the other two headings
        # already had -- this panel used to have none, leaving that one heading flush against
        # the panel above it while its siblings had real space.
        # rotate matches the comp's .quali-block exactly (0.8deg).
        box_style="padding:22px 22px 26px;", wrapper_style="margin:44px 0 40px;transform:rotate(0.8deg);",
    )


_GAP_VALUE_RE = re.compile(r"[\d.]+")
# Chunky bars, not a thin progress-bar sliver: the ask was to see the gap before reading the
# number, which needs real visual weight. Fixed px (not %) -- a percentage-width div inside a
# shrink-to-content table cell has nothing stable to be a percentage OF in Gmail, so it would
# either collapse or silently no-op depending on client. Floored at BAR_MIN_PX so the smallest
# real gap in a field is still a visible mark, not a sliver that reads as a rendering bug.
_BAR_MAX_PX = 240
_BAR_MIN_PX = 18


def _nb_pace_spread_html(pace_spread: dict | None) -> str:
    if pace_spread is None:
        return ""
    fastest = html.escape(pace_spread["fastest"])
    pace_rows = pace_spread["rows"]
    gap_values = []
    for _name, gap in pace_rows:
        m = _GAP_VALUE_RE.search(gap)
        gap_values.append(float(m.group()) if m else 0.0)
    max_gap = max(gap_values) if gap_values else 0.0
    # Table rows, not display:flex (unsupported for most real Gmail recipients) -- the
    # <tr><td>label</td><td align=right>value</td></tr> idiom is already Gmail-safe. Each team
    # is two stacked rows (name+value, then a full-width bar row) so the divider lands after
    # the bar and reads as one team's block ending, not a line through the middle of it.
    row_html = []
    for i, ((name, gap), value) in enumerate(zip(pace_rows, gap_values)):
        color = _team_color(name)
        # attempt 7 item 3: the gap figure used to be darkened via _readable_on_light for
        # contrast, which visibly drifted several teams' text away from their real hex (Ferrari
        # red went dull, Mercedes teal went murky) while the swatch right next to it stayed the
        # true color -- the two no longer matched. Team color now lives only on the swatch and
        # bar (solid fills, always legible at any hue); the figure itself is plain ink, so
        # there's no color to drift and nothing to darken.
        is_last = i == len(pace_rows) - 1
        border = "" if is_last else "border-bottom:1px dashed #0a0a0a55;"
        bar_px = _BAR_MAX_PX if max_gap == 0 else max(_BAR_MIN_PX, round(value / max_gap * _BAR_MAX_PX))
        row_html.append(
            "<tr>"
            f'<td style="padding:5px 28px 0 0;font-size:18px;text-align:left;">'
            f'<span class="swatch" style="background:{color}"></span>{html.escape(name)}</td>'
            f'<td style="padding:5px 0 0 8px;text-align:right;'
            f'font-family:{_NB_DISPLAY_FONT};font-weight:700;'
            f'font-size:28px;color:{_NB_INK};">{html.escape(gap)}</td>'
            "</tr>"
            f'<tr><td colspan="2" style="padding:6px 0 9px;{border}">'
            f'<div style="width:{bar_px}px;max-width:100%;height:11px;background:{color};'
            f'border-radius:2px;"></div>'
            "</td></tr>"
        )
    inner = (
        f'<p style="font-size:15px;margin:0 0 10px;">{fastest} set the pace this weekend. '
        f"Here&rsquo;s how much time the next three lost, every single lap.</p>"
        f'<table role="presentation" cellpadding="0" cellspacing="0">{"".join(row_html)}</table>'
    )
    return (
        '<span class="section-title">SUNDAY&rsquo;S FRONT RUNNERS</span>'
        + _nb_shadow_box(
            inner, box_class="flat-panel-inner",
            box_style="padding:14px 22px 16px;", wrapper_style="margin-bottom:40px;",
        )
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
        days_stat = f'<td style="padding-right:28px;"><b>{days}</b><span class="stat-label">days away</span></td>'
    length_km = next_race.get("length_km")
    km_stat = (
        f'<td><b>{length_km:.3f}</b><span class="stat-label">km circuit</span></td>'
        if length_km is not None else ""
    )
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

    cards_html = ""
    if insights:
        cards = []
        for i, ins in enumerate(insights, start=1):
            header = _clean(ins.header)
            body = _clean(_first_sentence(ins.explanation_email))
            color = _team_color(ins.team) if ins.team else _NB_INK
            # The number used to be a circular badge overlapping the card's corner (a fixed-
            # size sticker rendered before the card, which pulled itself up via negative
            # margin -- see the WINNER sticker's comment for that construction). Folded inside
            # the card instead, as a small team-colored tag ahead of the heading: one less
            # moving part, and it reads as a section marker rather than a stuck-on sticker.
            # Text color was hardcoded white, which fails contrast against light team colors
            # even in light mode (Cadillac gold, ~1.5:1) -- _on_color picks per-team like every
            # other solid-fill chip already does (stamps, sector labels, quali label). As a side
            # effect this also fixes the dark-mode simulation: a dark _on_color pick (ink) turns
            # light under Gmail's measured transform while a medium-light team-color background
            # turns dark, landing on light-text-on-dark instead of dark-transforming-to-dark.
            num_tag = f'<span class="nb-num" style="background:{color};color:{_on_color(color)}">{i:02d}</span>'
            # Alternating shadow direction + a slight counter-rotation on even cards matches the
            # comp's :nth-child(odd)/:nth-child(even) collage motif directly -- both transform
            # and the shadow's own side are confirmed supported, so there's no longer a reason
            # to flatten every card to the same right-side shadow.
            is_even = i % 2 == 0
            box = _nb_shadow_box(
                f"{num_tag}<h3>{header}</h3><p>{body}</p>",
                border_color=color, border_width="3px", box_class="insight-inner",
                box_style="padding:22px 20px 24px;", offset=5, side="left" if is_even else "right",
                wrapper_style=f"margin:0 0 20px;{'transform:rotate(-0.4deg);' if is_even else ''}",
            )
            cards.append(box)
        cards_html = '<span class="section-title">YOUR 3 INSIGHTS</span>' + "".join(cards)

    # Inline color (not the .cta class alone): Gmail's default link-blue was winning over
    # class-only anchor color in the attempt-2 send. Shadow-boxed like the panels; the anchor
    # itself is the inset content box so it stays a single click target.
    # Outlined + shrink-wrapped (inline=True), not a full-width solid red slab: as a solid bar
    # it was the single loudest element on the page and pulled focus off the data, which is the
    # actual product. Red border + red text on the off-white panel bg keeps it unmistakably the
    # action without out-shouting the insight cards.
    cta = _nb_shadow_box(
        f'<a href="{html.escape(cta_url)}" style="display:block;text-align:center;'
        f'font-family:{_NB_DISPLAY_FONT};font-weight:700;font-size:15px;color:#E10600;'
        'text-decoration:none;padding:11px 18px;">READ THE FULL ANALYSIS</a>',
        border_color="#E10600", inline=True, box_class="cta-inner",
        # rotate matches the comp's .cta exactly (-0.5deg).
        wrapper_style="margin:20px 0 50px;transform:rotate(-0.5deg);",
    )

    # attempt 6: the WINNER stamp used to float in its own row above this box and tuck under it
    # via a negative margin -- a different right edge than the panel it belonged to, and negative
    # margins are dropped outright by Yahoo/AOL per this comment's prior history. Moved inside
    # the panel's own top-left instead: one box, one left edge, nothing to misalign.
    # attempt 7 item 2: was filled with the true team color, so WINNER's text color had to be
    # picked per-team by luminance (black on McLaren papaya) -- reads inconsistent and, per
    # feedback, wrong for at least McLaren. Black fill sidesteps the whole per-team contrast
    # question: white text is always safely legible on it, for every team including the
    # lighter ones, with no darkening logic needed.
    winner_stamp = (
        f'<div style="margin-bottom:14px;">{_nb_stamp("WINNER", bg=_NB_INK, fg="#fff", inline=True)}</div>'
        if raw_team else ""
    )
    headline_box = _nb_shadow_box(
        f'{winner_stamp}{_nb_headline_html(winner)}{_nb_sub_html(winner, pace_spread)}',
        box_class="headline-inner",
        # rotate matches the comp's .headline-block exactly (-0.6deg).
        box_style="padding:22px 24px 28px;", wrapper_style="margin-bottom:40px;transform:rotate(-0.6deg);",
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8">
{_META_COLOR_SCHEME}
<title>Telogify &mdash; {event_name}</title>
{_NB_FONTS_LINK}
<style>{_NB_STYLE}</style>
</head>
<body>
<div class="page">
<div class="sheet">

  <div class="masthead">
    {_nb_stamp(event_name)}
    <table role="presentation" cellpadding="0" cellspacing="0" align="center" style="margin:18px auto 0;"><tr>
      <td style="padding-right:10px;vertical-align:middle;">{_nb_logo_chip(base_url)}</td>
      <td style="vertical-align:middle;"><p class="wordmark" style="margin:0;">Telo<span>gify</span></p></td>
    </tr></table>
  </div>

  {headline_box}

  {_nb_practice_html(practice)}
  {_nb_qualifying_html(quali_insight)}
  {_nb_pace_spread_html(pace_spread)}
  {cards_html}

  {cta}

  {_nb_next_race_html(next_race)}

  <p class="closer">See you after the next session!</p>

  <footer>
    Methodology inputs come from Mirco Bartolozzi (@fdataanalysis), covering clean-air filtering, fuel correction, and the ERS depletion signal. Timing data comes from FastF1.<br>
    &copy; {weekend.year} Tanish Misra<br>
    <a href="{html.escape(base_url.rstrip('/'))}/unsubscribe" style="color:#0a0a0a">Unsubscribe</a>
  </footer>

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


def render_digest_preview(year: int, round: int, db: Session) -> str:
    """Render the digest HTML for local preview. Never touches RESEND_API_KEY, never writes to
    the DB."""
    weekend, insights = _load_weekend_and_insights(year, round, db)
    return render_email_neubrutalist(
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
    html_body = render_email_neubrutalist(weekend, insights, settings.web_base_url, **extras)
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
