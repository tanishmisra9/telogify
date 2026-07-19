from datetime import datetime, timedelta, timezone

import pandas as pd

from telogify.analysis.schedule import Event, completed_rounds, fetch_season_schedule, pick_next_event

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


def test_completed_rounds_includes_past_excludes_future():
    events = [_ev(1, "Past", -10), _ev(2, "Today", 0), _ev(3, "Future", 5)]
    assert completed_rounds(events, BASE) == [1, 2]


def test_completed_rounds_excludes_round_zero():
    events = [Event(round=0, name="Test", date=BASE - timedelta(days=1)), _ev(1, "GP", -1)]
    assert completed_rounds(events, BASE) == [1]


def test_completed_rounds_sorted():
    events = [_ev(3, "C", -3), _ev(1, "A", -10), _ev(2, "B", -5)]
    assert completed_rounds(events, BASE) == [1, 2, 3]


def test_picks_earliest_date_regardless_of_input_order():
    events = [_ev(5, "Far", 20), _ev(2, "Near", 3)]
    assert pick_next_event(events, BASE).name == "Near"


# --- fetch_season_schedule: FastF1 boundary mocked --------------------------


def test_fetch_season_schedule_maps_rows_with_fallbacks_and_tz(monkeypatch):
    import fastf1

    from telogify.ingest import fastf1_cache

    sched = pd.DataFrame(
        [
            {  # tz-aware Session5DateUtc -> converted to naive UTC
                "Session5DateUtc": pd.Timestamp("2026-07-05 13:00:00", tz="UTC"),
                "Session5Date": pd.NaT,
                "EventDate": pd.NaT,
                "RoundNumber": 1,
                "EventName": "British Grand Prix",
                "Country": "United Kingdom",
                "Location": "Silverstone",
            },
            {  # Session5DateUtc missing -> falls back to Session5Date
                "Session5DateUtc": pd.NaT,
                "Session5Date": pd.Timestamp("2026-07-12 14:00:00"),
                "EventDate": pd.NaT,
                "RoundNumber": 2,
                "EventName": "Belgian Grand Prix",
                "Country": "Belgium",
                "Location": "Spa",
            },
            {  # both session dates missing -> falls back to EventDate
                "Session5DateUtc": pd.NaT,
                "Session5Date": pd.NaT,
                "EventDate": pd.Timestamp("2026-07-19"),
                "RoundNumber": 3,
                "EventName": "Hungarian Grand Prix",
                "Country": "Hungary",
                "Location": "Budapest",
            },
            {  # every date missing -> skipped entirely
                "Session5DateUtc": pd.NaT,
                "Session5Date": pd.NaT,
                "EventDate": pd.NaT,
                "RoundNumber": 4,
                "EventName": "Testing",
                "Country": "",
                "Location": "",
            },
        ]
    )
    monkeypatch.setattr(fastf1, "get_event_schedule", lambda year, include_testing=False: sched)
    monkeypatch.setattr(fastf1_cache, "enable_cache", lambda: None)

    events = fetch_season_schedule(2026)

    assert [e.round for e in events] == [1, 2, 3]
    assert events[0].date == datetime(2026, 7, 5, 13, 0, 0)  # tz stripped, still 13:00 UTC
    assert events[0].date.tzinfo is None
    assert events[1].date == datetime(2026, 7, 12, 14, 0, 0)
    assert events[2].date == datetime(2026, 7, 19, 0, 0, 0)
    assert events[0].name == "British Grand Prix"
    assert events[0].country == "United Kingdom"


def test_fetch_season_schedule_returns_empty_tuple_on_failure(monkeypatch):
    import fastf1

    def boom(year, include_testing=False):
        raise RuntimeError("network down")

    monkeypatch.setattr(fastf1, "get_event_schedule", boom)

    assert fetch_season_schedule(2026) == ()
