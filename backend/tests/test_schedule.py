from datetime import datetime, timedelta

from telogify.analysis.schedule import Event, pick_next_event

BASE = datetime(2026, 7, 2, 12, 0, 0)


def _ev(round: int, name: str, days: float) -> Event:
    return Event(round=round, name=name, date=BASE + timedelta(days=days))


def test_picks_soonest_future_event():
    events = [_ev(1, "Past", -5), _ev(3, "Later", 10), _ev(2, "Soon", 3)]
    nxt = pick_next_event(events, BASE)
    assert nxt is not None and nxt.name == "Soon"


def test_now_is_not_after_now():
    # An event exactly at `now` does not count as upcoming.
    assert pick_next_event([_ev(1, "Now", 0), _ev(2, "Past", -1)], BASE) is None


def test_end_of_season_returns_none():
    assert pick_next_event([_ev(1, "A", -30), _ev(2, "B", -1)], BASE) is None


def test_empty_returns_none():
    assert pick_next_event([], BASE) is None


def test_picks_earliest_date_regardless_of_input_order():
    events = [_ev(5, "Far", 20), _ev(2, "Near", 3)]
    assert pick_next_event(events, BASE).name == "Near"
