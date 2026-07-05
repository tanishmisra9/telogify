"""Pick the next upcoming F1 event from a season schedule, so the landing-page countdown
can tick toward it. Pure and datetime-only; the FastF1 fetch that feeds it lives in
fetch_season_schedule, keeping pick_next_event and completed_rounds unit-testable offline.
Event dates must all share tz-awareness (fetch_season_schedule normalizes to naive UTC)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Event:
    round: int
    name: str
    date: datetime
    country: str = ""
    location: str = ""  # host city/circuit locality


def pick_next_event(events: list[Event], now: datetime) -> Event | None:
    """Earliest event whose date is strictly after `now`, or None when the season is over
    or the schedule is empty."""
    upcoming = [e for e in events if e.date > now]
    if not upcoming:
        return None
    return min(upcoming, key=lambda e: e.date)


def fetch_season_schedule(year: int) -> tuple[Event, ...]:
    """FastF1 season schedule mapped to Event rows (naive UTC dates). Returns () on failure."""
    try:
        import fastf1
        import pandas as pd

        sched = fastf1.get_event_schedule(year, include_testing=False)
    except Exception:
        return ()

    events: list[Event] = []
    for _, r in sched.iterrows():
        # Prefer the race-session start; fall back to the event date.
        raw = r.get("Session5DateUtc")
        if raw is None or pd.isna(raw):
            raw = r.get("Session5Date")
        if raw is None or pd.isna(raw):
            raw = r.get("EventDate")
        if raw is None or pd.isna(raw):
            continue
        dt = pd.Timestamp(raw).to_pydatetime()
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        events.append(
            Event(
                round=int(r.get("RoundNumber") or 0),
                name=str(r.get("EventName") or ""),
                date=dt,
                country=str(r.get("Country") or ""),
                location=str(r.get("Location") or ""),
            )
        )
    return tuple(events)


def completed_rounds(events: Sequence[Event], now: datetime) -> list[int]:
    """Round numbers whose race session date is on or before `now`, sorted ascending."""
    return sorted(e.round for e in events if e.round > 0 and e.date <= now)
