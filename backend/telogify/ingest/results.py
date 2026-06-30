"""Session results / finishing order ingest.

For race and sprint sessions FastF1's results `Time` column is already the gap to the
winner for P2 and below (winner holds total time), so the leader's gap is 0 and the
rest take `Time` directly. Non-race sessions have no meaningful finishing gap.
`compute_gap` is pure and tested.
"""

from dataclasses import dataclass

import pandas as pd
from sqlmodel import Session as DBSession
from sqlmodel import delete, select

from telogify.ingest.loader import WeekendData
from telogify.models import Session, SessionResult

_RACE_LIKE = {"Race", "Sprint"}


@dataclass
class ResultRow:
    position: int | None
    driver: str
    constructor: str | None
    gap_to_leader: float | None
    status: str | None


def compute_gap(position: int | None, time_s: float | None, is_race: bool) -> float | None:
    if not is_race or time_s is None:
        return None
    return 0.0 if position == 1 else float(time_s)


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def extract_results(session) -> list[ResultRow]:
    res = session.results
    is_race = session.name in _RACE_LIKE
    rows: list[ResultRow] = []
    for _, r in res.iterrows():
        pos = _int(r.get("Position"))
        time = r.get("Time")
        time_s = time.total_seconds() if pd.notna(time) else None
        rows.append(
            ResultRow(
                position=pos,
                driver=r.get("Abbreviation"),
                constructor=r.get("TeamName"),
                gap_to_leader=compute_gap(pos, time_s, is_race),
                status=r.get("Status"),
            )
        )
    rows.sort(key=lambda x: (x.position is None, x.position or 0))
    return rows


def store_results(data: WeekendData, db: DBSession) -> None:
    for code, session in data.sessions.items():
        row = db.exec(
            select(Session).where(
                Session.weekend_id == data.weekend.id, Session.session_type == code
            )
        ).first()
        if row is None:
            continue
        db.exec(delete(SessionResult).where(SessionResult.session_id == row.id))
        for r in extract_results(session):
            db.add(
                SessionResult(
                    session_id=row.id,
                    position=r.position,
                    driver=r.driver,
                    constructor=r.constructor,
                    gap_to_leader=r.gap_to_leader,
                    status=r.status,
                )
            )
    db.commit()
