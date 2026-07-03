"""Pick the next upcoming F1 event from a season schedule, so the landing-page countdown
can tick toward it. Pure and datetime-only; the FastF1 fetch that feeds it lives in the API
layer, keeping this unit-testable offline. Event dates must all share tz-awareness (the API
layer normalizes to naive UTC before calling in)."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Event:
    round: int
    name: str
    date: datetime


def pick_next_event(events: list[Event], now: datetime) -> Event | None:
    """Earliest event whose date is strictly after `now`, or None when the season is over
    or the schedule is empty."""
    upcoming = [e for e in events if e.date > now]
    if not upcoming:
        return None
    return min(upcoming, key=lambda e: e.date)
