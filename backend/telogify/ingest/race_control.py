"""Race control events: the official on-track record (collisions, incidents, penalties, safety
cars, retirements), parsed from FastF1's race_control_messages.

This is the only source that tells the insight agent *why* a car finished far below its pace
(a collision, a penalty) rather than leaving it to invent a tyre-wear or straight-line cause
for a result an on-track incident actually caused. Stored per race/sprint session, idempotently.

`parse_race_control` is pure and unit-tested offline.
"""

import re
from dataclasses import dataclass

from sqlmodel import Session as DBSession
from sqlmodel import delete, select

from telogify.ingest.loader import WeekendData
from telogify.models import RaceControlEvent, Session

_CODE_RE = re.compile(r"\((\w{3})\)")
_RACE_SESSIONS = ("R", "SPRINT")  # only here does an incident explain a finishing position
# procedural follow-ups and track-limit lap deletions are noise, not events
_NOISE = ("NO FURTHER", "UNDER INVESTIGATION", "WILL BE INVESTIGATED", "REVIEWED", "DELETED")


@dataclass(frozen=True)
class ParsedEvent:
    lap: int | None
    driver: str | None  # 3-letter code; None for track-wide events (safety car)
    kind: str
    message: str


def _classify(msg_upper: str) -> str | None:
    """Notable event kind for a race control message, or None to drop it. Keeps the initial
    call and any served penalty; drops the investigation/review chain and lap-time deletions."""
    if any(n in msg_upper for n in _NOISE):
        return None
    if "PENALTY" in msg_upper:
        return "penalty"
    if "COLLISION" in msg_upper:
        return "collision"
    if "FORCING ANOTHER DRIVER OFF" in msg_upper:
        return "forced_off"
    if "SAFETY CAR" in msg_upper:
        return "safety_car"
    if "RETIRED" in msg_upper or "STOPPED ON" in msg_upper:
        return "retirement"
    if "INCIDENT" in msg_upper and "NOTED" in msg_upper:
        return "incident"
    return None


def parse_race_control(messages: list[dict]) -> list[ParsedEvent]:
    """messages: dicts with Lap and Message. Returns notable, de-duplicated events, one row per
    car mentioned (or one driverless row for a track-wide event like a safety car)."""
    out: list[ParsedEvent] = []
    seen: set = set()
    for m in messages:
        msg = str(m.get("Message") or "").strip()
        if not msg:
            continue
        kind = _classify(msg.upper())
        if kind is None:
            continue
        raw = m.get("Lap")
        try:
            lap = int(raw) if raw is not None and str(raw).strip() not in ("", "nan", "None") else None
        except (ValueError, TypeError):
            lap = None
        for drv in _CODE_RE.findall(msg) or [None]:
            key = (drv, kind, msg)
            if key in seen:
                continue
            seen.add(key)
            out.append(ParsedEvent(lap=lap, driver=drv, kind=kind, message=msg))
    return out


def store_race_control(data: WeekendData, db: DBSession) -> None:
    for code, session in data.sessions.items():
        if code not in _RACE_SESSIONS:
            continue
        row = db.exec(
            select(Session).where(Session.weekend_id == data.weekend.id, Session.session_type == code)
        ).first()
        if row is None:
            continue
        try:
            records = session.race_control_messages.to_dict("records")
        except Exception:
            records = []
        db.exec(delete(RaceControlEvent).where(RaceControlEvent.session_id == row.id))
        for ev in parse_race_control(records):
            db.add(
                RaceControlEvent(
                    session_id=row.id, lap=ev.lap, driver=ev.driver, kind=ev.kind, message=ev.message
                )
            )
    db.commit()
