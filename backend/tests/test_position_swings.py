"""Tests for position-swing miner (POSITION_SWING_MIN boundary). Uses test DB only."""

from sqlmodel import Session

from telogify.analysis.candidates import (
    POSITION_SWING_MIN,
    _mine_position_swings,
    _mine_position_swings_for_pair,
)
from telogify.models import RaceWeekend, Session as SessionRow, SessionResult


def test_position_swing_min_filters_small_swings(test_engine):
    with Session(test_engine) as db:
        wk = RaceWeekend(year=2026, round=96, circuit_name="X", country="Y", event_name="Swing Test")
        db.add(wk)
        db.commit()
        db.refresh(wk)

        quali = SessionRow(weekend_id=wk.id, session_type="Q", status="loaded")
        race = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
        db.add(quali)
        db.add(race)
        db.commit()
        db.refresh(quali)
        db.refresh(race)

        dc_map = {"VER": "Red Bull", "NOR": "McLaren", "LEC": "Ferrari"}

        # At cap: grid 5 -> finish 3 = swing 2 (kept). Below cap: grid 5 -> finish 4 = swing 1 (dropped).
        for driver, grid, finish in [("VER", 5, 3), ("NOR", 5, 4), ("LEC", 10, 10)]:
            db.add(SessionResult(session_id=quali.id, driver=driver, position=grid, constructor=dc_map[driver]))
            db.add(SessionResult(session_id=race.id, driver=driver, position=finish, constructor=dc_map[driver]))
        db.commit()

        signals = _mine_position_swings_for_pair(db, quali, race, dc_map, "position_swing", "R")
        assert len(signals) == 1
        assert signals[0].subject == "Red Bull"
        assert signals[0].magnitude == POSITION_SWING_MIN
        assert signals[0].source_refs[0]["positions_gained"] == POSITION_SWING_MIN


def test_position_swing_skips_missing_grid_and_missing_constructor(test_engine):
    with Session(test_engine) as db:
        wk = RaceWeekend(year=2026, round=97, circuit_name="X", country="Y", event_name="Swing Test 2")
        db.add(wk)
        db.commit()
        db.refresh(wk)

        quali = SessionRow(weekend_id=wk.id, session_type="Q", status="loaded")
        race = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
        db.add(quali)
        db.add(race)
        db.commit()
        db.refresh(quali)
        db.refresh(race)

        # ALO: no quali result at all -> grid.get() is None, skipped.
        db.add(SessionResult(session_id=race.id, driver="ALO", position=3, constructor="Aston Martin"))
        # SAI: qualified but DNF'd (no race position) -> skipped.
        db.add(SessionResult(session_id=quali.id, driver="SAI", position=8, constructor="Williams"))
        db.add(SessionResult(session_id=race.id, driver="SAI", position=None, constructor="Williams"))
        # STR: big swing but neither dc_map nor the race row has a constructor -> skipped.
        db.add(SessionResult(session_id=quali.id, driver="STR", position=9, constructor=None))
        db.add(SessionResult(session_id=race.id, driver="STR", position=2, constructor=None))
        db.commit()

        signals = _mine_position_swings_for_pair(db, quali, race, {}, "position_swing", "R")
        assert signals == []


def test_mine_position_swings_sprint_branch(test_engine):
    with Session(test_engine) as db:
        wk = RaceWeekend(year=2026, round=98, circuit_name="X", country="Y", event_name="Sprint Swing Test")
        db.add(wk)
        db.commit()
        db.refresh(wk)

        sq = SessionRow(weekend_id=wk.id, session_type="SQ", status="loaded")
        sprint = SessionRow(weekend_id=wk.id, session_type="SPRINT", status="loaded")
        db.add(sq)
        db.add(sprint)
        db.commit()
        db.refresh(sq)
        db.refresh(sprint)

        dc_map = {"VER": "Red Bull"}
        db.add(SessionResult(session_id=sq.id, driver="VER", position=5, constructor="Red Bull"))
        db.add(SessionResult(session_id=sprint.id, driver="VER", position=1, constructor="Red Bull"))
        db.commit()

        signals = _mine_position_swings(db, [sq, sprint], dc_map)
        assert len(signals) == 1
        assert signals[0].signal_type == "sprint_position_swing"
