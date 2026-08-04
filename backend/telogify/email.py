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
from urllib.parse import urlencode

from sqlmodel import Session
from sqlmodel import select

from telogify.analysis.attribution import _driver_constructor_map
from telogify.analysis.constructor_index import _race_stints_as_dicts
from telogify.analysis.race_pace import constructor_median_gaps
from telogify.analysis.schedule import fetch_season_schedule, pick_next_event
from telogify.analysis.sectors import best_across_sessions, best_top_speeds, sector_dominance
from telogify.analysis.sessions import pick_session
from telogify.chipgen import measure_text_chip
from telogify.config import settings
from telogify.db import set_service_scope
from telogify.subscriptions import VERIFY_TOKEN_TTL_HOURS, unsubscribe_token
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


def _team_swatch_url(base_url: str, hex_color: str) -> str:
    """A hosted, solid-color PNG for `hex_color` (frontend/public/team-colors/, one file per
    distinct value in _TEAM_COLORS + _MUTED -- generated once via
    emailsim.probe._solid_png_data_uri, not at request time, since the palette is fixed in code).
    Measured (emailsim Probe E, 2026-08-02): a real hosted image's own color survives Gmail's
    dark-mode rewriting where the same color as CSS background does not -- delta 78 from the
    original color vs. delta 262 from what the CSS-inversion curve predicts, confirmed against
    a real Gmail dark-mode screenshot. A single small square scales cleanly to any on-page size
    via width/height (or background-size), so this one file serves both the fixed-size swatch
    and the variable-width pace bar."""
    return f"{base_url.rstrip('/')}/team-colors/{hex_color.lstrip('#').lower()}.png"


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


def _unsub_link(base_url: str, unsub_token: str | None) -> str:
    """Per-recipient unsubscribe URL, or the bare page when there is no subscriber row behind
    the address (an ad-hoc --to send, or a preview render). The bare form lands on the page's
    "missing code" state, which tells the reader to use the link from a real digest."""
    base = f"{base_url.rstrip('/')}/unsubscribe"
    return f"{base}?t={unsub_token}" if unsub_token else base


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
    unsub_token: str | None = None,
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
    lines.append(f"Unsubscribe: {_unsub_link(base_url, unsub_token)}")

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
# Measured against real Gmail sends (backend/telogify/emailsim/, support.py's measured CSS
# support matrix) that Gmail (desktop webmail + iOS/Android, the overwhelming majority of
# recipients) strips or ignores: transform (no rotation, any platform -- so none is used here
# at all anymore), box-shadow (also proven false on iOS after initially misreading as
# supported; see _nb_shadow_box's own note), the left/right/top/bottom offsets a
# position:absolute element needs to actually be positioned, display:flex/grid, border-radius,
# clip-path, and CSS custom properties (var() references survive, :root declarations don't --
# N/A here, Neubrutalist never used them). Grid/flex rows, the WINNER sticker, and the insight
# number badges are table-based / normal-flow instead of relying on those properties; the
# collage's depth comes from _nb_shadow_box's nested-box shadow fake, which needs none of them.
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
    """Fakes a hard offset-shadow with two nested boxes instead of CSS box-shadow. CORRECTED
    2026-08-02: this briefly switched to real box-shadow on the belief emailsim's Probe B had
    confirmed it supported on Gmail iOS -- that verdict was itself a false positive (Probe B's
    original test couldn't distinguish "shadow rendered" from "shadow offset ignored, box just
    sits there"; see support.py's box_shadow correction). Direct pixel measurement of a real
    send showed a plain single-line border with zero shadow growth. Back to the nested-box fake:
    an outer div painted the shadow color, with the visible content box inset from it via
    ordinary positive margin, so the shadow color peeks out as a real color discontinuity.
    background-color and margin are both universally supported, unlike box-shadow. `side` flips
    which edges the inset margin (and therefore the visible shadow) sits on, for the insight
    cards' alternating shadow direction. `wrapper_style` carries the outer box's own margin
    (kept as a separate param from `box_style`'s inner padding since they land on different
    elements again now)."""
    display = "inline-block" if inline else "block"
    margin = f"0 {offset}px {offset}px 0" if side == "right" else f"0 0 {offset}px {offset}px"
    cls = f' class="{box_class}"' if box_class else ""
    return (
        f'<div style="display:{display};background:{shadow_color};{wrapper_style}">'
        f'<div{cls} style="background:{bg};border:{border_width} solid {border_color};margin:{margin};{box_style}">'
        f"{inner_html}"
        "</div></div>"
    )


def _nb_logo_chip(base_url: str) -> str:
    """The masthead icon: one hosted flat PNG (frontend/public/logo-chip.png) baking in the
    whole shadow-box look (white backdrop, black border, the icon itself), not a live CSS box
    around a hosted <img>. CORRECTED 2026-08-02: the live version (white background + black
    border) is exactly the failure case this whole project's dark-mode work is about -- under
    Gmail's automatic inversion, the white background crushes toward black while the black
    border lifts toward white, flipping to a white-bordered black box (measured on a real send:
    "changes... to a white border black favicon in dark mode"). A single baked image is immune
    to that rewriting, so it renders identically regardless of theme -- the whole point of every
    other image-based fix in this file (team-color swatches, etc.)."""
    logo_url = f"{base_url.rstrip('/')}/logo-chip.png"
    return f'<img src="{html.escape(logo_url)}" width="46" height="50" alt="" style="display:block;width:46px;height:50px;">'


# Section-title chips (frontend/public/chips/chip-section-*.png): the three panel headings below
# are always the exact same word-for-word string with the same fixed black/white color scheme,
# regardless of weekend, so -- like WINNER and the masthead logo above -- they're safe to
# pre-bake once and serve as a STATIC hosted image, immune to Gmail's dark-mode CSS rewriting.
# Everything else that's still team-colored or per-weekend text (driver name, event name, sector/
# qualifying/next-up labels, insight-number badges) can't be pre-baked this way since its text
# and/or color changes every weekend -- see _dynamic_chip_img below for those instead.
_SECTION_TITLE_CHIPS = {
    "practice": ("chip-section-practice.png", "FAST OUT THE GATES IN PRACTICE", 414, 38),
    "pace": ("chip-section-pace.png", "SUNDAY&rsquo;S FRONT RUNNERS", 337, 38),
    "insights": ("chip-section-insights.png", "YOUR 3 INSIGHTS", 220, 38),
}


def _nb_section_title_chip(base_url: str, key: str) -> str:
    filename, alt, width, height = _SECTION_TITLE_CHIPS[key]
    url = f"{base_url.rstrip('/')}/chips/{filename}"
    return (
        f'<img src="{html.escape(url)}" width="{width}" height="{height}" alt="{alt}" '
        f'style="display:inline-block;vertical-align:middle;margin-bottom:28px;">'
    )


def _dynamic_chip_img(
    text: str,
    *,
    font_size: int,
    text_color: str,
    bg_color: str | None = None,
    padding: tuple[int, int, int, int] = (0, 0, 0, 0),
    border_radius: int = 0,
    style_extra: str = "",
) -> str:
    """<img> tag for team-colored/per-weekend-dynamic text (driver name, event name, sector/
    qualifying/next-up labels, insight numbers): served on demand at send time by
    telogify.api.routes' /chip/text.png (chipgen.py), since unlike WINNER/section-titles above,
    neither the text nor the color is fixed across weekends, so a one-time static file can't
    represent it. Width/height come from chipgen.measure_text_chip with the exact same arguments
    passed in the URL, so what /chip/text.png later serves always matches the size this <img> tag
    already told Gmail to expect. See chipgen.py's module docstring for the full background."""
    width, height = measure_text_chip(text, font_size=font_size, padding=padding)
    params: dict[str, str | int] = {"text": text, "font_size": font_size, "text_color": text_color}
    if bg_color is not None:
        params["bg_color"] = bg_color
    if border_radius:
        params["border_radius"] = border_radius
    top, right, bottom, left = padding
    for name, value in (
        ("padding_top", top), ("padding_right", right),
        ("padding_bottom", bottom), ("padding_left", left),
    ):
        if value:
            params[name] = value
    url = f"{settings.api_base_url.rstrip('/')}/chip/text.png?{urlencode(params)}"
    return (
        f'<img src="{html.escape(url)}" width="{width}" height="{height}" '
        f'alt="{html.escape(text)}" style="display:inline-block;vertical-align:middle;{style_extra}">'
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
  /* Wider on desktop, where a 700px column looks like a narrow island in the message pane's own
     open space. Only reachable clients: mobile Gmail (the majority) ignores media queries
     entirely (this whole file's dark-mode saga is about exactly that), so this never affects a
     phone; a real wide viewport (desktop webmail, Apple Mail) picks it up correctly. */
  @media (min-width: 720px) {{
    .sheet {{ max-width: 900px; }}
    .pace-bar {{ max-width: 100%; }}
  }}
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
  /* attempt 8: the solid highlight box read as loud/bad across every real send regardless of
     theme -- plain text instead, no background. attempt 9: red read worse than black next to
     the team-colored name right before it, so plain ink. */
  .headline .verdict {{ color: #0a0a0a; }}
  .sub {{ font-size: 16px; line-height: 1.6; margin-top: 14px; max-width: 56ch; }}
  .sub b {{ background: #FFE500; padding: 0 3px; }}
  .swatch {{ display:inline-block; width:14px; height:14px; margin-right:8px; border:1px solid #0a0a0a; vertical-align:middle; }}
  /* The real per-row cap is an inline max-width set in Python (see _nb_pace_spread_html: each
     row's own calc((100% - 140px) * ratio), so a clamped row stays proportional to the others
     instead of every clamped bar converging on the same flat ceiling regardless of its real
     value -- measured wrong on a real narrow phone before this). This class is only the fallback
     for a client that doesn't parse calc() at all, in which case the inline value is also
     invalid and ignored, falling through to this flat 45%; untested against a real send, unlike
     everything else in this file's CSS support notes. */
  .pace-bar {{ max-width: 45%; }}
  .practice-tile-inner {{ font-size: 13px; }}
  .practice-tile-inner .val {{ font-family: {_NB_DISPLAY_FONT}; font-weight: 700; font-size: 20px; margin: 2px 0; }}
  .quali-inner h3 {{ font-family: {_NB_DISPLAY_FONT}; font-weight: 700; font-size: 21px; margin: 12px 0 8px; line-height: 1.15; }}
  .quali-inner p {{ font-size: 14px; line-height: 1.6; margin: 0; max-width: 54ch; }}
  .insight-inner h3 {{ font-family: {_NB_DISPLAY_FONT}; font-weight: 700; font-size: 19px; margin: 0 0 8px; line-height: 1.2; }}
  .insight-inner p {{ font-size: 14px; line-height: 1.65; margin: 0; }}
  .next-race-inner h3 {{ font-family: {_NB_DISPLAY_FONT}; font-weight: 700; font-size:24px; margin:12px 0 6px; }}
  .next-race-inner .stats {{ margin-top:14px; font-size:13px; }}
  /* item 7: label sits to the right of the number, baseline-aligned ("27 days away" as one
     phrase), not stacked below it -- the old display:block on b pushed the label onto its own
     line under the figure. */
  .next-race-inner .stats b {{ font-family: {_NB_DISPLAY_FONT}; font-weight: 700; font-size:22px; color:#E10600; margin-right:6px; }}
  .next-race-inner .stats .stat-label {{ font-size:16px; color:#0a0a0a; }}
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
    /* Same explicit-declaration-wins-over-inheritance issue as everything else in this block:
       .stat-label's own class rule (color:#0a0a0a) has higher specificity than the group
       .next-race-inner rule's inherited light text, so "days away"/"km circuit" stayed ink-on-
       dark and nearly vanished. Caught in the same desktop-width dark-mode screenshot check
       that found the other three. */
    .next-race-inner .stat-label {{ color: #d8d8c8; }}
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
    A single line at one uniform size: the driver's full name in the team's real color,
    immediately followed by the verdict in plain brand red (attempt 8: a solid highlight box
    there read as loud/bad on every real send). Hierarchy comes from color alone, not a mix of
    sizes or boxes, so the line aligns and wraps evenly by construction."""
    raw_team = winner["constructor"] if winner and winner.get("constructor") else None
    full_name = _full_driver_name(winner["driver"]) if winner else None
    name = full_name.upper() if full_name else None
    team = html.escape(raw_team) if raw_team else None
    team_color = _team_color(raw_team) if raw_team else "#E10600"

    if name and team:
        # Dynamic chip, not live `color:{team_color}` CSS: a real send measured the driver name's
        # bright team color (e.g. Mercedes teal) crushed by Gmail's dark-mode inversion. See
        # _dynamic_chip_img's docstring.
        name_chip = _dynamic_chip_img(name, font_size=28, text_color=team_color)
        spans = (
            f'{name_chip} '
            f'<span class="verdict">WON FOR {team.upper()}!</span>'
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


def _nb_practice_html(practice: dict | None, base_url: str) -> str:
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
    # this into one stacked column.
    # The label sits flush against the tile's own top-left corner (zero padding on the outer
    # box itself), with the rest of the content padded by an inner wrapper instead -- negative
    # margin was tried first to pull the label back out through the box's padding, verified at
    # exactly 0px in Chromium, but real Gmail did not honor it (a gap remained), so the
    # zero-outer-padding/inner-wrapper structure avoids relying on negative margin at all.
    tile_divs = [
        _nb_shadow_box(
            _dynamic_chip_img(
                label, font_size=11, text_color=_on_color(_team_color(constructor)),
                bg_color=_team_color(constructor), padding=(1, 6, 1, 6),
                style_extra="margin-bottom:6px;",
            )
            + f'<div style="padding:0 16px 18px;">'
            f'<p class="val">{html.escape(value)}{mph_html}</p>'
            f'<p style="margin:0;">{html.escape(constructor)} &middot; {html.escape(driver_bit)}</p>'
            f'</div>',
            border_width="1.5px", offset=3.5, box_class="practice-tile-inner",
            box_style="padding:0;",
        )
        for label, value, constructor, driver_bit, mph_html in tiles
    ]
    rows_html = "".join(
        '<tr>'
        f'<td width="50%" style="padding:0 9px 18px 0;vertical-align:top;">{tile_divs[r]}</td>'
        f'<td width="50%" style="padding:0 0 18px 9px;vertical-align:top;">{tile_divs[r + 1]}</td>'
        '</tr>'
        for r in range(0, len(tile_divs), 2)
    )
    return (
        _nb_section_title_chip(base_url, "practice")
        + f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows_html}</table>'
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
    # QUALIFYING HOUR sits flush against the box's own top-left corner (zero padding on the
    # outer box), with the heading/body padded by an inner wrapper instead -- see the headline
    # box's own comment for why this avoids negative margin entirely (verified 0px in Chromium,
    # not honored by real Gmail).
    inner = (
        _dynamic_chip_img(
            "QUALIFYING HOUR", font_size=12, text_color=_on_color(lbl_color), bg_color=lbl_color,
            padding=(3, 10, 3, 10),
        )
        + f'<div style="padding:12px 24px 28px;"><h3>{header}</h3>'
        f'<p>{body}</p></div>'
    )
    return _nb_shadow_box(
        inner, bg=team_color, box_class="quali-inner",
        # margin-bottom matches headline_box's own 40px, so the section-title after this panel
        # (PACE SPREAD // CONSTRUCTORS) gets the same breathing room the other two headings
        # already had -- this panel used to have none, leaving that one heading flush against
        # the panel above it while its siblings had real space.
        box_style="padding:0;", wrapper_style="margin:44px 0 40px;",
    )


_GAP_VALUE_RE = re.compile(r"[\d.]+")
# Chunky bars, not a thin progress-bar sliver: the ask was to see the gap before reading the
# number, which needs real visual weight. Fixed px (not %) -- a percentage-width div inside a
# shrink-to-content table cell has nothing stable to be a percentage OF in Gmail, so it would
# either collapse or silently no-op depending on client. Floored at BAR_MIN_PX so the smallest
# real gap in a field is still a visible mark, not a sliver that reads as a rendering bug.
# 240 (attempt 7) was tuned for the mobile-only 514px card; left a lot of unused width once the
# card widened to 900px on desktop (the bar's own `max-width:100%` already protects mobile
# regardless of how big this constant is, so raising it is a free win there, not a tradeoff).
# 420 -> 520: the gap figure now sits inline right after its own bar (see row_html below) instead
# of in a separate right-aligned column, so there's no longer a reserved value column eating into
# the card's width -- bars can grow further before the figure needs room.
_BAR_MAX_PX = 520
_BAR_MIN_PX = 18


def _nb_pace_spread_html(pace_spread: dict | None, base_url: str) -> str:
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
        swatch_url = _team_swatch_url(base_url, color)
        # attempt 7 item 3: the gap figure used to be darkened via _readable_on_light for
        # contrast, which visibly drifted several teams' text away from their real hex (Ferrari
        # red went dull, Mercedes teal went murky) while the swatch right next to it stayed the
        # true color -- the two no longer matched. Team color now lives only on the swatch and
        # bar (solid fills, always legible at any hue); the figure itself is plain ink, so
        # there's no color to drift and nothing to darken.
        # Swatch and bar render as a hosted image, not a CSS background (see _team_swatch_url):
        # a CSS-colored Mercedes swatch crushes to near-invisible on real Gmail dark mode, the
        # image does not.
        is_last = i == len(pace_rows) - 1
        border = "" if is_last else "border-bottom:1px dashed #0a0a0a55;"
        ratio = 1.0 if max_gap == 0 else value / max_gap
        bar_px = _BAR_MAX_PX if max_gap == 0 else max(_BAR_MIN_PX, round(ratio * _BAR_MAX_PX))
        # The gap figure sits inline right after its OWN bar, in the same cell -- not a separate
        # right-aligned column. A separate column shares one width across every row (set by the
        # widest bar), so a shorter row's value lands far past where its own bar actually ends;
        # only the longest bar happened to look flush. Inline placement tracks each row's real
        # bar length instead.
        # max-width is per-row proportional, not a flat cap: a flat calc(100% - 140px) ceiling
        # (same for every row) measured wrong on a real narrow phone -- once a bar's intrinsic
        # width (bar_px, scaled for the wide desktop card) exceeds that flat ceiling, EVERY such
        # row clamps to the identical width, so McLaren (+0.371s) and Red Bull Racing (+0.594s)
        # rendered as the same-length bar despite a 60% real difference. Scaling the ceiling by
        # this row's own ratio keeps every clamped row proportional to the others: since bar_px
        # is itself `ratio * _BAR_MAX_PX`, intrinsic width exceeds this row's ceiling exactly when
        # it does for every other row (the ratio cancels out of that comparison), so either every
        # row clamps in unison at its own correct fraction of the available space, or none do.
        row_html.append(
            "<tr>"
            f'<td colspan="2" style="padding:5px 0 0 0;font-size:18px;text-align:left;">'
            f'<img class="swatch" src="{swatch_url}" width="14" height="14" alt="">{html.escape(name)}</td>'
            "</tr>"
            f'<tr><td colspan="2" style="padding:6px 0 9px;{border}">'
            f'<img class="pace-bar" src="{swatch_url}" width="{bar_px}" height="11" alt="" '
            f'style="display:inline-block;vertical-align:middle;width:{bar_px}px;height:11px;'
            f'border-radius:2px;max-width:calc((100% - 140px) * {ratio:.4f});">'
            f'<span style="display:inline-block;vertical-align:middle;margin-left:10px;'
            f'font-family:{_NB_DISPLAY_FONT};font-weight:700;'
            f'font-size:28px;color:{_NB_INK};">{html.escape(gap)}</span>'
            "</td></tr>"
        )
    inner = (
        f'<p style="font-size:15px;margin:0 0 10px;">{fastest} set the pace this weekend. '
        f"Here&rsquo;s how much time the next three lost, every single lap.</p>"
        # width="100%" alone isn't enough: table-layout defaults to auto, which still grows the
        # table past 100% if a row's content (the unbreakable bar+value run) needs more room --
        # and the bar's max-width (see .pace-bar) would then resolve against that inflated width
        # instead of the card's real one, a feedback loop that measured as the table overflowing
        # the card's own border on a real narrow render. table-layout:fixed makes the 100%
        # authoritative, so the percentage/calc() cap finally has a real, bounded width to work OF.
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="table-layout:fixed;">{"".join(row_html)}</table>'
    )
    return (
        _nb_section_title_chip(base_url, "pace")
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
        f'<p style="margin:0;font-size:16px;">{html.escape(next_race["place"])}</p>'
        if next_race.get("place") else ""
    )
    # NEXT UP sits flush against the box's own top-left corner (zero padding on the outer box),
    # with the rest padded by an inner wrapper instead -- see the headline box's own comment for
    # why (negative margin verified 0px in Chromium, not honored by real Gmail).
    inner = (
        _dynamic_chip_img(
            f'NEXT UP · ROUND {next_race["round"]}', font_size=11, text_color="#fff",
            bg_color="#E10600", padding=(3, 9, 3, 9),
        )
        + f'<div style="padding:12px 24px 26px;"><h3>{html.escape(next_race["name"])}</h3>{place}'
        # Table row, not display:flex+gap (unsupported for most Gmail recipients) -- was
        # collapsing "4 days away" / "4.381 km circuit" into one run-on line with no spacing.
        f'<table role="presentation" cellpadding="0" cellspacing="0" class="stats"><tr>{days_stat}{km_stat}</tr></table></div>'
    )
    return _nb_shadow_box(
        inner, box_class="next-race-inner", box_style="padding:0;",
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
    unsub_token: str | None = None,
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
            # other solid-fill chip already does (stamps, sector labels, quali label). Now a
            # dynamic image (like the other team-colored chips), so this renders exactly as
            # authored in every client regardless of theme -- no dark-mode transform to reason
            # about at all, unlike when this was still live CSS.
            num_tag = _dynamic_chip_img(
                f"{i:02d}", font_size=12, text_color=_on_color(color), bg_color=color,
                padding=(4, 9, 4, 9), border_radius=3, style_extra="margin-bottom:14px;",
            )
            # Alternating shadow direction on even cards matches the comp's
            # :nth-child(odd)/:nth-child(even) collage motif -- the shadow's own side is
            # confirmed supported, so there's no reason to flatten every card to the same
            # right-side shadow.
            is_even = i % 2 == 0
            # The number badge sits flush against the card's own top-left corner (zero padding
            # on the outer box), heading/body padded by an inner wrapper instead -- see the
            # headline box's own comment for why (negative margin verified 0px in Chromium, not
            # honored by real Gmail).
            box = _nb_shadow_box(
                f'{num_tag}<div style="padding:0 22px 26px;"><h3>{header}</h3><p>{body}</p></div>',
                border_color=color, border_width="3px", box_class="insight-inner",
                box_style="padding:0;", offset=5, side="left" if is_even else "right",
                wrapper_style="margin:0 0 20px;",
            )
            cards.append(box)
        cards_html = _nb_section_title_chip(base_url, "insights") + "".join(cards)

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
        wrapper_style="margin:20px 0 50px;",
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
    # Hosted image, not live CSS: WINNER's text is always the same word with the same fixed
    # black/white color scheme (never team-dependent), so unlike the driver name or team-colored
    # labels elsewhere in this email, it's safe to pre-bake once -- and doing so makes it immune
    # to Gmail's automatic dark-mode color rewriting, which was flipping the live version to a
    # white box with black text on a real send. See CLAUDE.md's Email digest section for the
    # full "Variant C" background on which elements are safe to pre-bake (fixed text AND fixed
    # color) versus which still need live CSS (dynamic team color and/or per-weekend text).
    winner_stamp = (
        f'<div style="margin-bottom:14px;"><img src="{html.escape(base_url.rstrip("/"))}/chips/'
        f'chip-winner.png" width="138" height="52" alt="WINNER" style="display:block;"></div>'
        if raw_team else ""
    )
    # WINNER sits flush against the box's own top-left corner (zero padding on the outer box),
    # with the rest of the content padded by an inner wrapper instead -- negative margin was
    # tried first to pull WINNER back through the box's padding, verified at exactly 0px in
    # Chromium, but real Gmail did not honor it (a visible gap remained), so this avoids relying
    # on negative margin at all. Without a winner (no team), there's no stamp to supply the top
    # gap via its own margin, so the wrapper needs the full top padding itself.
    content_padding_top = "0" if winner_stamp else "22px"
    headline_box = _nb_shadow_box(
        f'{winner_stamp}<div style="padding:{content_padding_top} 24px 28px 24px;">'
        f'{_nb_headline_html(winner)}{_nb_sub_html(winner, pace_spread)}</div>',
        box_class="headline-inner",
        box_style="padding:0;", wrapper_style="margin-bottom:40px;",
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
    {_dynamic_chip_img(
        weekend.event_name, font_size=15, text_color=_on_color("#E10600"), bg_color="#E10600",
        padding=(10, 18, 10, 18),
    )}
    <table role="presentation" cellpadding="0" cellspacing="0" align="center" style="margin:18px auto 0;"><tr>
      <td style="padding-right:10px;vertical-align:middle;">{_nb_logo_chip(base_url)}</td>
      <td style="vertical-align:middle;"><p class="wordmark" style="margin:0;">Telo<span>gify</span></p></td>
    </tr></table>
  </div>

  {headline_box}

  {_nb_practice_html(practice, base_url)}
  {_nb_qualifying_html(quali_insight)}
  {_nb_pace_spread_html(pace_spread, base_url)}
  {cards_html}

  {cta}

  {_nb_next_race_html(next_race)}

  <p class="closer">See you after the next session!</p>

  <footer>
    Methodology inputs come from <a href="https://www.instagram.com/fdataanalysis/" style="color:#0a0a0a">Mirco Bartolozzi (@fdataanalysis)</a>, covering clean-air filtering, fuel correction, and the ERS depletion signal. Timing data comes from FastF1.<br>
    &copy; {weekend.year} Tanish Misra<br>
    <a href="{html.escape(_unsub_link(base_url, unsub_token))}" style="color:#0a0a0a">Unsubscribe</a>
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
        # subscriber is under FORCE row level security (security_sql.py); without service scope
        # this select returns zero rows and the digest would silently send to nobody.
        set_service_scope(db)
        recipients = [
            s.email
            for s in db.exec(select(Subscriber).where(Subscriber.status == "confirmed")).all()
        ]
    if not recipients:
        return 0

    import resend

    resend.api_key = settings.resend_api_key
    extras = _load_extras(db, weekend)
    subject = f"{weekend.event_name}: your 3 insights"

    # Per-recipient unsubscribe: the token identifies the row, so it cannot be shared or reused
    # across addresses. Looked up here rather than threaded through the renderers, which stay
    # pure. Falls back to an untokenized link only for an ad-hoc --to address that is not a
    # subscriber at all, where there is nothing to unsubscribe.
    set_service_scope(db)
    ids_by_email = {
        s.email: s.id for s in db.exec(select(Subscriber).where(Subscriber.email.in_(recipients))).all()
    }

    for email in recipients:
        subscriber_id = ids_by_email.get(email)
        token = unsubscribe_token(subscriber_id) if subscriber_id is not None else None
        # Rendered per recipient because the unsubscribe link is per recipient. The expensive
        # part (_load_extras, which hits the DB) is already hoisted out of this loop.
        payload: dict = {
            "from": settings.resend_from,
            "to": [email],
            "subject": subject,
            "html": render_email_neubrutalist(
                weekend, insights, settings.web_base_url, unsub_token=token, **extras
            ),
            "text": render_email_plaintext(
                weekend, insights, settings.web_base_url, unsub_token=token, **extras
            ),
        }
        if token is not None:
            payload["headers"] = list_unsubscribe_headers(token)
        resend.Emails.send(payload)
    return len(recipients)


# ---------------------------------------------------------------------------
# Transactional opt-in emails (verification + welcome).
#
# These live here, not in a module of their own, because every primitive they need is already
# module-level in this file: _nb_shadow_box, _nb_logo_chip, _dynamic_chip_img and _NB_STYLE.
# A separate module would have meant either duplicating the document shell or extracting a
# shared kit, and extracting it would have meant re-deriving the digest's shell to serve two
# very different layouts. The digest's own f-string is deliberately left untouched.
#
# Same Gmail constraints as the digest, from emailsim/support.py: no box-shadow (the nested-div
# fake in _nb_shadow_box), no border-radius, no transform, no negative margin, no data: URIs,
# tables for layout, and anchor color inline rather than by class because Gmail's default
# link-blue beats a class-only rule.
# ---------------------------------------------------------------------------


def list_unsubscribe_headers(unsub_token: str) -> dict[str, str]:
    """RFC 8058 one-click headers, so Gmail and Apple Mail render their native Unsubscribe
    button. Required for bulk senders and a real deliverability signal.

    The URL points at the API, not the frontend: mail providers POST to it server side, so it
    has to be an endpoint rather than a page. `/unsubscribe` accepts the token as a query
    parameter with no body, which is what lets one endpoint serve both this and the page.
    """
    return {
        "List-Unsubscribe": (
            f"<{settings.api_base_url.rstrip('/')}/unsubscribe?t={unsub_token}>"
        ),
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }


def _nb_cta(url: str, label: str) -> str:
    """The digest's CTA treatment, as a helper, for the two opt-in emails."""
    return _nb_shadow_box(
        f'<a href="{html.escape(url)}" style="display:block;text-align:center;'
        f'font-family:{_NB_DISPLAY_FONT};font-weight:700;font-size:15px;color:#E10600;'
        f'text-decoration:none;padding:11px 18px;">{html.escape(label)}</a>',
        border_color="#E10600", inline=True, box_class="cta-inner",
        wrapper_style="margin:24px 0 28px;",
    )


def _optin_shell(*, title: str, stamp_text: str, body_html: str, footer_html: str) -> str:
    """Masthead + sheet + footer for a transactional email. Narrower than the digest's shell
    because these carry one message and one action, not eight sections."""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8">
{_META_COLOR_SCHEME}
<title>{html.escape(title)}</title>
{_NB_FONTS_LINK}
<style>{_NB_STYLE}</style>
</head>
<body>
<div class="page">
<div class="sheet">

  <div class="masthead">
    {_dynamic_chip_img(
        stamp_text, font_size=15, text_color=_on_color("#E10600"), bg_color="#E10600",
        padding=(10, 18, 10, 18),
    )}
    <table role="presentation" cellpadding="0" cellspacing="0" align="center" style="margin:18px auto 0;"><tr>
      <td style="padding-right:10px;vertical-align:middle;">{_nb_logo_chip(settings.web_base_url)}</td>
      <td style="vertical-align:middle;"><p class="wordmark" style="margin:0;">Telo<span>gify</span></p></td>
    </tr></table>
  </div>

{body_html}

  <footer>
{footer_html}
  </footer>

</div>
</div>
</body>
</html>"""


def verify_url(token: str) -> str:
    return f"{settings.web_base_url.rstrip('/')}/subscribe/verify?t={token}"


def unsubscribe_url(unsub_token: str) -> str:
    return f"{settings.web_base_url.rstrip('/')}/unsubscribe?t={unsub_token}"


def render_verification_email(token: str) -> str:
    link = verify_url(token)
    body = f"""
  <p style="font-family:{_NB_SANS_FONT};font-size:16px;line-height:1.55;color:#0a0a0a;margin:26px 0 0;">
    You asked for three telemetry-grounded insights after every race weekend.
    Confirm this address and your seat is locked in.
  </p>

{_nb_cta(link, "CONFIRM MY SEAT")}

  <p style="font-family:{_NB_SANS_FONT};font-size:13px;line-height:1.5;color:#555;margin:0 0 22px;">
    Button not working? Paste this into your browser:<br>
    <a href="{html.escape(link)}" style="color:#0a0a0a;word-break:break-all;">{html.escape(link)}</a>
  </p>

  <p style="font-family:{_NB_SANS_FONT};font-size:13px;line-height:1.5;color:#555;margin:0;">
    This link expires in {VERIFY_TOKEN_TTL_HOURS} hours. If you did not ask for this, ignore it
    and nothing happens. Nobody joins the grid without this click.
  </p>
"""
    # No unsubscribe link: there is nothing to unsubscribe from until this is confirmed.
    footer = (
        "    You are receiving this because this address was entered at "
        f"{html.escape(settings.web_base_url.rstrip('/'))}.<br>\n"
        f"    &copy; {datetime.utcnow().year} Tanish Misra"
    )
    return _optin_shell(
        title="Confirm your seat on the grid",
        stamp_text="CONFIRM YOUR SEAT",
        body_html=body,
        footer_html=footer,
    )


def render_verification_plaintext(token: str) -> str:
    return "\n".join([
        "CONFIRM YOUR SEAT",
        "",
        "You asked for three telemetry-grounded insights after every race weekend.",
        "Confirm this address and your seat is locked in:",
        "",
        verify_url(token),
        "",
        f"This link expires in {VERIFY_TOKEN_TTL_HOURS} hours. If you did not ask for this,",
        "ignore it and nothing happens. Nobody joins the grid without this click.",
    ])


def render_welcome_email(unsub_token: str) -> str:
    body = f"""
  <p style="font-family:{_NB_DISPLAY_FONT};font-weight:700;font-size:26px;line-height:1.15;color:#0a0a0a;margin:26px 0 0;">
    Your seat is confirmed.
  </p>

  <p style="font-family:{_NB_SANS_FONT};font-size:16px;line-height:1.55;color:#0a0a0a;margin:14px 0 0;">
    After every race weekend you get three insights built from the session telemetry, not from
    the broadcast: what the cars actually did through the corners, on the straights, and over a
    stint. Plus two reads on qualifying pace and the constructor pace spread.
  </p>

{_nb_cta(f"{settings.web_base_url.rstrip('/')}/weekends", "SEE THE LATEST WEEKEND")}
"""
    footer = (
        f"    &copy; {datetime.utcnow().year} Tanish Misra<br>\n"
        f'    <a href="{html.escape(unsubscribe_url(unsub_token))}" style="color:#0a0a0a">Unsubscribe</a>'
    )
    return _optin_shell(
        title="Lights out. You are on the grid.",
        stamp_text="LIGHTS OUT",
        body_html=body,
        footer_html=footer,
    )


def render_welcome_plaintext(unsub_token: str) -> str:
    return "\n".join([
        "LIGHTS OUT. YOU ARE ON THE GRID.",
        "",
        "Your seat is confirmed.",
        "",
        "After every race weekend you get three insights built from the session telemetry,",
        "not from the broadcast: what the cars actually did through the corners, on the",
        "straights, and over a stint. Plus two reads on qualifying pace and the constructor",
        "pace spread.",
        "",
        f"See the latest weekend: {settings.web_base_url.rstrip('/')}/weekends",
        "",
        f"Unsubscribe: {unsubscribe_url(unsub_token)}",
    ])


def _send(to: str, subject: str, html_body: str, text_body: str,
          headers: dict[str, str] | None = None) -> None:
    """Single Resend call. No-ops without an API key so local signup works end to end without
    one, and so tests never need to reach the network."""
    if not settings.resend_api_key:
        return
    import resend

    resend.api_key = settings.resend_api_key
    payload: dict = {
        "from": settings.resend_from,
        "to": [to],
        "subject": subject,
        "html": html_body,
        "text": text_body,
    }
    if headers:
        payload["headers"] = headers
    resend.Emails.send(payload)


def send_verification_email(to: str, token: str) -> None:
    _send(
        to,
        "Confirm your seat on the grid",
        render_verification_email(token),
        render_verification_plaintext(token),
    )


def send_welcome_email(to: str, unsub_token: str) -> None:
    _send(
        to,
        "Lights out. You are on the grid.",
        render_welcome_email(unsub_token),
        render_welcome_plaintext(unsub_token),
        headers=list_unsubscribe_headers(unsub_token),
    )
