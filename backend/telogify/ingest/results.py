"""Session results / finishing order ingest.

For race and sprint sessions FastF1's results `Time` column is the gap to the leader
for on-lead-lap finishers only. Lapped drivers carry `Status` = "Lapped" and a `Time`
that is their gap to the car ahead, not the leader, so it must not be shown as a
leader gap. Use the `Laps` column vs the winner's lap count for "+N Lap(s)" instead.
`compute_gap` is pure and tested.
"""

from dataclasses import dataclass

import pandas as pd
from sqlmodel import Session as DBSession
from sqlmodel import delete, select

from telogify.ingest.loader import WeekendData
from telogify.models import Session, SessionResult

_RACE_LIKE = {"Race", "Sprint"}
_QUALI_LIKE = {"Qualifying", "Sprint Qualifying", "Sprint Shootout"}


@dataclass
class ResultRow:
    position: int | None
    driver: str
    constructor: str | None
    gap_to_leader: float | None
    total_time_s: float | None
    laps: float | None
    status: str | None
    q1_time_s: float | None = None
    q2_time_s: float | None = None
    q3_time_s: float | None = None


# Championship points by finishing position for a race. The fastest-lap point was
# removed for 2025+, so for the seasons this app targets points are a pure function
# of position. (Sprints use a different scale, but this table serves the race panel.)
_RACE_POINTS = {1: 25, 2: 18, 3: 15, 4: 12, 5: 10, 6: 8, 7: 6, 8: 4, 9: 2, 10: 1}
_SPRINT_POINTS = {1: 8, 2: 7, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1}

_COMPOUND_LETTER = {"SOFT": "S", "MEDIUM": "M", "HARD": "H", "INTERMEDIATE": "I", "WET": "W"}


def race_points(position: int | None) -> int:
    return _RACE_POINTS.get(position, 0) if position else 0


def sprint_points(position: int | None) -> int:
    return _SPRINT_POINTS.get(position, 0) if position else 0


def points_for_session(session_type: str, position: int | None) -> int:
    """Championship points for a finishing position. Sprint uses the 8-deep scale; every other
    session type uses the grand-prix table. Callers should only pass race or sprint sessions."""
    if session_type == "SPRINT":
        return sprint_points(position)
    return race_points(position)


def compound_letter(compound: str | None) -> str:
    if not compound:
        return "?"
    return _COMPOUND_LETTER.get(compound.upper(), compound[:1].upper())


def strategy_string(compounds: list[str | None]) -> str:
    """Compound sequence as letters, e.g. ['MEDIUM','HARD','MEDIUM'] -> 'M-H-M'."""
    return "-".join(compound_letter(c) for c in compounds)


def format_total_time(seconds: float | None) -> str | None:
    """Winner's total race time as H:MM:SS.mmm (hours dropped when zero)."""
    if seconds is None:
        return None
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    if hours:
        return f"{hours}:{minutes:02d}:{secs:06.3f}"
    return f"{minutes}:{secs:06.3f}"


def is_lapped(
    status: str | None,
    laps: float | None,
    leader_laps: float | None,
) -> bool:
    if status == "Lapped":
        return True
    if laps is not None and leader_laps is not None and laps < leader_laps:
        return True
    return False


def laps_down(laps: float | None, leader_laps: float | None) -> int | None:
    if laps is None or leader_laps is None:
        return None
    down = int(round(leader_laps - laps))
    return down if down > 0 else None


def format_gap_label(
    position: int | None,
    gap_to_leader: float | None,
    laps: float | None,
    leader_laps: float | None,
    status: str | None,
) -> str:
    """Human-readable gap for the results table and agent tools."""
    if position == 1:
        return "leader"

    status = (status or "").strip()
    sl = status.lower()
    if sl == "retired":
        return "DNF"
    if sl == "did not start":
        return "DNS"

    if is_lapped(status, laps, leader_laps):
        down = laps_down(laps, leader_laps)
        if down == 1:
            return "+1 Lap"
        if down and down > 1:
            return f"+{down} Laps"
        return "+1 Lap"

    if gap_to_leader is not None:
        return f"+{gap_to_leader:.1f}s"

    return status


def compute_gap(
    position: int | None,
    time_s: float | None,
    is_race: bool,
    *,
    status: str | None = None,
    laps: float | None = None,
    leader_laps: float | None = None,
) -> float | None:
    if not is_race:
        return None
    if position == 1:
        return 0.0
    if is_lapped(status, laps, leader_laps):
        return None
    if time_s is None:
        return None
    return float(time_s)


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value) -> float | None:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _segment_time_s(row, column: str) -> float | None:
    value = row.get(column)
    if value is None or pd.isna(value):
        return None
    return value.total_seconds()


def extract_results(session) -> list[ResultRow]:
    res = session.results
    is_race = session.name in _RACE_LIKE
    is_quali = session.name in _QUALI_LIKE

    leader_laps: float | None = None
    if is_race:
        leaders = res[res["Position"] == 1]
        if len(leaders):
            leader_laps = _float(leaders.iloc[0].get("Laps"))

    rows: list[ResultRow] = []
    for _, r in res.iterrows():
        pos = _int(r.get("Position"))
        time = r.get("Time")
        time_s = time.total_seconds() if pd.notna(time) else None
        laps = _float(r.get("Laps"))
        status = r.get("Status")
        rows.append(
            ResultRow(
                position=pos,
                driver=r.get("Abbreviation"),
                constructor=r.get("TeamName"),
                gap_to_leader=compute_gap(
                    pos,
                    time_s,
                    is_race,
                    status=status,
                    laps=laps,
                    leader_laps=leader_laps,
                ),
                # For the winner, FastF1's Time is the total race time (not a gap).
                total_time_s=time_s if (is_race and pos == 1) else None,
                laps=laps,
                status=status,
                q1_time_s=_segment_time_s(r, "Q1") if is_quali else None,
                q2_time_s=_segment_time_s(r, "Q2") if is_quali else None,
                q3_time_s=_segment_time_s(r, "Q3") if is_quali else None,
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
                    total_time_s=r.total_time_s,
                    laps=r.laps,
                    status=r.status,
                    q1_time_s=r.q1_time_s,
                    q2_time_s=r.q2_time_s,
                    q3_time_s=r.q3_time_s,
                )
            )
    db.commit()
