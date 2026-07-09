"""Pure Wikipedia wikitext parsing: section split, session mapping, fact extraction."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

SESSION_TYPES = ("SQ", "SPRINT", "Q", "R")

# Longest alias first within each session type (matched case-insensitively).
_SESSION_ALIASES: dict[str, tuple[str, ...]] = {
    "SQ": ("sprint qualifying report", "sprint qualifying", "sprint shootout"),
    "SPRINT": ("sprint report", "sprint race", "sprint"),
    "Q": ("qualifying report", "qualifying"),
    "R": ("race report", "race"),
}

_SKIP_HEADINGS = frozenset(
    {
        "classification",
        "championship standings",
        "entries",
        "entry list",
        "background",
        "practice",
        "free practice",
        "fp1",
        "fp2",
        "fp3",
        "results",
        "qualifying classification",
        "race classification",
        "sprint classification",
    }
)

_RECAP_BLOCKLIST = (
    "maiden",
    "first win",
    "this season",
    "championship",
    "debut",
    "pole to flag",
    "back-to-back",
    "consecutive",
)

_DRIVER_CODES = (
    "ALB",
    "ALO",
    "ANT",
    "BEA",
    "BOR",
    "BOT",
    "COL",
    "GAS",
    "HAD",
    "HAM",
    "HUL",
    "LAW",
    "LEC",
    "LIN",
    "NOR",
    "OCO",
    "PER",
    "PIA",
    "RUS",
    "SAI",
    "STR",
    "VER",
)

# Wikipedia prose uses full names; map surname (lowercase) to 3-letter code.
_SURNAME_TO_CODE: dict[str, str] = {
    "albon": "ALB",
    "alonso": "ALO",
    "antonelli": "ANT",
    "bearman": "BEA",
    "bortoleto": "BOR",
    "bottas": "BOT",
    "colapinto": "COL",
    "gasly": "GAS",
    "hadjar": "HAD",
    "hamilton": "HAM",
    "hulkenberg": "HUL",
    "lawson": "LAW",
    "leclerc": "LEC",
    "lindblad": "LIN",
    "norris": "NOR",
    "ocon": "OCO",
    "perez": "PER",
    "pérez": "PER",
    "piastri": "PIA",
    "russell": "RUS",
    "sainz": "SAI",
    "stroll": "STR",
    "verstappen": "VER",
}

_SECTION_RE = re.compile(r"^={2,}\s*(.+?)\s*={2,}\s*$", re.MULTILINE)
_TEMPLATE_RE = re.compile(r"\{\{[^{}]*(?:\{\{[^{}]*\}\}[^{}]*)*\}\}", re.DOTALL)
_REF_RE = re.compile(r"<ref[^>]*>.*?</ref>", re.DOTALL | re.IGNORECASE)
_REF_SELF_RE = re.compile(r"<ref[^>]*/>", re.IGNORECASE)
_CATEGORY_RE = re.compile(r"\[\[Category:[^\]]+\]\]", re.IGNORECASE)
_WIKILINK_RE = re.compile(r"\[\[([^|\]]+\|)?([^\]]+)\]\]")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_TABLE_ROW_RE = re.compile(r"^\{\|.*", re.MULTILINE)

_LAP_RE = re.compile(r"\b(?:on |after |at )?lap\s+(\d+)\b", re.IGNORECASE)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

_KEYWORD_SCORES: tuple[tuple[str, int, str], ...] = (
    (r"\bretired\b|\bdnf\b|\bdid not finish\b", 100, "retirement"),
    (r"\bcoolant\b|\bengine\b|\bgearbox\b|\bhydraulic\b|\bpower unit\b", 95, "retirement"),
    (r"\bdamage\b|\bdamaged\b|\bbodywork\b|\bwheel shield\b|\bbroken\b", 92, "damage"),
    (r"\bcollision\b|\bcollided\b|\bcrashed\b", 90, "collision"),
    (r"\btrack limits\b|\bexceeding track limits\b", 88, "penalty"),
    (r"\bpenalty\b|\bpenalised\b|\bpenalized\b", 85, "penalty"),
    (r"\bvirtual safety car\b|\bvsc\b", 80, "safety_car"),
    (r"\bsafety car\b", 75, "safety_car"),
    (r"\bred flag\b", 70, "safety_car"),
    (r"\bpit stop\b|\bthree-stop\b|\btwo-stop\b|\bone-stop\b|\bstrategy\b", 60, "strategy"),
    (r"\brain\b|\bwet\b|\bintermediate\b", 50, "weather"),
)

_MAX_FACTS = 6
_MAX_FACTS_RACE = 8
_PROTAGONIST_SWING_MIN = 5
_PROTAGONIST_BOOST = 50
_RESERVED_SWING_SLOTS = 2
_MAX_FACT_CHARS = 140
_MAX_SUMMARY_CHARS = 200


@dataclass
class RecapFact:
    kind: str
    lap: int | None
    drivers: list[str]
    text: str


@dataclass
class SessionRecap:
    present: bool = False
    summary: str = ""
    facts: list[RecapFact] = field(default_factory=list)

    def to_dict(self) -> dict:
        if not self.present:
            return {"present": False}
        return {
            "present": True,
            "summary": self.summary,
            "facts": [
                {
                    "kind": f.kind,
                    "lap": f.lap,
                    "drivers": f.drivers,
                    "text": f.text,
                }
                for f in self.facts
            ],
        }


def strip_wikitext_noise(text: str) -> str:
    """Remove templates, refs, categories; flatten wikilinks to display text."""
    out = text
    out = _REF_RE.sub(" ", out)
    out = _REF_SELF_RE.sub(" ", out)
    out = _TEMPLATE_RE.sub(" ", out)
    out = _CATEGORY_RE.sub(" ", out)
    out = _WIKILINK_RE.sub(r"\2", out)
    out = _HTML_TAG_RE.sub(" ", out)
    out = re.sub(r"'''+?", "", out)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def split_wikitext_sections(wikitext: str) -> dict[str, str]:
    """Return {heading: body} for level-2+ sections."""
    matches = list(_SECTION_RE.finditer(wikitext))
    if not matches:
        return {}
    sections: dict[str, str] = {}
    for i, match in enumerate(matches):
        heading = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(wikitext)
        body = wikitext[start:end].strip()
        key = heading.lower()
        if key not in sections:
            sections[key] = body
    return sections


def _heading_matches_session(heading: str, session: str) -> bool:
    low = heading.lower().strip()
    if low in _SKIP_HEADINGS:
        return False
    for alias in _SESSION_ALIASES[session]:
        if alias not in low:
            continue
        if session == "SPRINT" and ("qualifying" in low or "shootout" in low):
            continue
        if session == "Q" and ("sprint" in low):
            continue
        if session == "R" and ("classification" in low or "post-race" in low or "championship" in low):
            continue
        return True
    return False


def _session_section_rank(session: str, heading: str, body: str) -> tuple[int, int, int]:
    """Prefer explicit *report* sections, then alias specificity, then body length."""
    low = heading.lower()
    report = 0 if "report" in low else 1
    alias_rank = len(_SESSION_ALIASES[session])
    for i, alias in enumerate(_SESSION_ALIASES[session]):
        if alias in low:
            alias_rank = i
            break
    return (report, alias_rank, -len(body))


def map_sections_to_sessions(sections: dict[str, str]) -> dict[str, str]:
    """Map Wikipedia section headings to SQ/SPRINT/Q/R bodies."""
    out: dict[str, str] = {}
    for session in SESSION_TYPES:
        candidates: list[tuple[str, str]] = []
        for heading, body in sections.items():
            if _heading_matches_session(heading, session):
                candidates.append((heading, body))
        if not candidates:
            continue
        candidates.sort(key=lambda item: _session_section_rank(session, item[0], item[1]))
        out[session] = candidates[0][1]
    return out


def _blocked_sentence(sentence: str) -> bool:
    low = sentence.lower()
    if any(b in low for b in _RECAP_BLOCKLIST):
        return True
    if "standings" in low or "championship" in low:
        return True
    if low.strip().startswith("{|") or "|-" in low:
        return True
    return False


def _score_sentence(sentence: str) -> tuple[int, str]:
    low = sentence.lower()
    best_score = 0
    best_kind = "other"
    for pattern, score, kind in _KEYWORD_SCORES:
        if re.search(pattern, low):
            if score > best_score:
                best_score = score
                best_kind = kind
    if best_score == 0 and len(sentence) > 40:
        best_score = 10
    return best_score, best_kind


def _extract_drivers(sentence: str) -> list[str]:
    found: list[str] = []
    for code in _DRIVER_CODES:
        if re.search(rf"\b{code}\b", sentence):
            found.append(code)
    low = sentence.lower()
    for surname, code in _SURNAME_TO_CODE.items():
        if code in found:
            continue
        if re.search(rf"\b{re.escape(surname)}\b", low):
            found.append(code)
    return found


def _protagonist_boost(sentence: str, protagonist_drivers: frozenset[str]) -> int:
    if not protagonist_drivers:
        return 0
    drivers = _extract_drivers(sentence)
    if any(d in protagonist_drivers for d in drivers):
        return _PROTAGONIST_BOOST
    return 0


def _mentions_protagonist(fact: RecapFact, protagonist_drivers: frozenset[str]) -> bool:
    if not protagonist_drivers:
        return False
    if any(d in protagonist_drivers for d in fact.drivers):
        return True
    return any(surname in fact.text.lower() for surname, code in _SURNAME_TO_CODE.items() if code in protagonist_drivers)


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0]
    return cut + "…" if cut else text[: limit - 1] + "…"


def extract_facts(
    section_text: str,
    *,
    session_type: str | None = None,
    protagonist_drivers: frozenset[str] | None = None,
) -> tuple[str, list[RecapFact]]:
    """Return (summary, facts) from one session section body."""
    cleaned = strip_wikitext_noise(section_text)
    if not cleaned:
        return "", []

    protagonists = protagonist_drivers or frozenset()
    max_facts = _MAX_FACTS_RACE if session_type == "R" else _MAX_FACTS

    # Drop table blocks early.
    if _TABLE_ROW_RE.search(section_text):
        lines = [ln for ln in cleaned.split(". ") if not ln.strip().startswith("|")]
        cleaned = ". ".join(lines)

    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(cleaned) if s.strip()]
    scored: list[tuple[int, str, str]] = []
    for sent in sentences:
        if len(sent) < 20 or _blocked_sentence(sent):
            continue
        score, kind = _score_sentence(sent)
        score += _protagonist_boost(sent, protagonists)
        if score > 0:
            scored.append((score, kind, sent))

    scored.sort(key=lambda x: (-x[0], x[2]))
    facts: list[RecapFact] = []
    seen_text: set[str] = set()
    for _, kind, sent in scored[: max_facts * 2]:
        short = _truncate(sent, _MAX_FACT_CHARS)
        key = short.lower()
        if key in seen_text:
            continue
        seen_text.add(key)
        lap_match = _LAP_RE.search(sent)
        lap = int(lap_match.group(1)) if lap_match else None
        facts.append(
            RecapFact(
                kind=kind,
                lap=lap,
                drivers=_extract_drivers(sent),
                text=short,
            )
        )
        if len(facts) >= max_facts:
            break

    if protagonists and session_type == "R" and facts:
        swing_facts: list[RecapFact] = []
        for _, kind, sent in scored:
            fact = RecapFact(
                kind=kind,
                lap=int(m.group(1)) if (m := _LAP_RE.search(sent)) else None,
                drivers=_extract_drivers(sent),
                text=_truncate(sent, _MAX_FACT_CHARS),
            )
            if _mentions_protagonist(fact, protagonists):
                swing_facts.append(fact)
        reserved = 0
        for swing_fact in swing_facts:
            if reserved >= _RESERVED_SWING_SLOTS:
                break
            if any(f.text.lower() == swing_fact.text.lower() for f in facts):
                continue
            if len(facts) >= max_facts:
                facts.pop()
            facts.append(swing_fact)
            reserved += 1

    summary = ""
    if scored:
        summary = _truncate(scored[0][2], _MAX_SUMMARY_CHARS)

    return summary, facts


def protagonist_drivers_from_swings(swings: dict[str, int], min_swing: int = _PROTAGONIST_SWING_MIN) -> frozenset[str]:
    """Driver codes with |grid-finish swing| at or above min_swing."""
    return frozenset(code for code, swing in swings.items() if abs(swing) >= min_swing)


def fact_mentions_driver(fact: dict, driver_code: str) -> bool:
    """True when a recap fact names the driver by code or surname."""
    if driver_code in (fact.get("drivers") or []):
        return True
    text = (fact.get("text") or "").lower()
    for surname, code in _SURNAME_TO_CODE.items():
        if code == driver_code and re.search(rf"\b{re.escape(surname)}\b", text):
            return True
    return False


def build_recap_payload(
    wikitext: str,
    session_types_present: set[str],
    protagonist_drivers: frozenset[str] | None = None,
) -> dict[str, dict]:
    """Parse wikitext into the sessions_json shape for present session types only."""
    sections = split_wikitext_sections(wikitext)
    mapped = map_sections_to_sessions(sections)
    protagonists = protagonist_drivers or frozenset()
    payload: dict[str, dict] = {}
    for session in SESSION_TYPES:
        if session not in session_types_present:
            continue
        body = mapped.get(session)
        if not body:
            payload[session] = {"present": False}
            continue
        summary, facts = extract_facts(
            body,
            session_type=session,
            protagonist_drivers=protagonists if session == "R" else None,
        )
        if not summary and not facts:
            payload[session] = {"present": False}
            continue
        recap = SessionRecap(present=True, summary=summary, facts=facts)
        payload[session] = recap.to_dict()
    return payload


def decode_toc_line(line: str) -> str:
    """Decode HTML entities in tocdata section lines."""
    return html.unescape(re.sub(r"<[^>]+>", "", line)).strip()
