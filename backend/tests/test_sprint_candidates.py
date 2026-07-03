"""Tests for sprint-specific candidate miners."""

from sqlmodel import Session

from telogify.analysis.candidates import _mine_sprint_vs_race_pace
from telogify.models import RaceWeekend, Session as SessionRow, Stint


def test_mine_sprint_vs_race_pace_emits_cross_event_signal(test_engine):
    with Session(test_engine) as db:
        wk = RaceWeekend(year=2026, round=1, circuit_name="X", country="Y", event_name="Sprint GP")
        db.add(wk)
        db.commit()
        db.refresh(wk)

        sprint = SessionRow(weekend_id=wk.id, session_type="SPRINT", status="loaded")
        race = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
        db.add(sprint)
        db.add(race)
        db.commit()
        db.refresh(sprint)
        db.refresh(race)

        db.add(Stint(
            session_id=sprint.id, driver="VER", stint_number=1, compound="MEDIUM",
            lap_times_json=[90.0, 90.0, 90.0, 90.0, 90.0, 90.0],
        ))
        db.add(Stint(
            session_id=sprint.id, driver="NOR", stint_number=1, compound="MEDIUM",
            lap_times_json=[91.0, 91.0, 91.0, 91.0, 91.0, 91.0],
        ))
        db.add(Stint(
            session_id=race.id, driver="VER", stint_number=1, compound="MEDIUM",
            lap_times_json=[92.0, 92.0, 92.0, 92.0, 92.0, 92.0],
        ))
        db.add(Stint(
            session_id=race.id, driver="NOR", stint_number=1, compound="MEDIUM",
            lap_times_json=[95.0, 95.0, 95.0, 95.0, 95.0, 95.0],
        ))
        db.commit()

        dc_map = {"VER": "Red Bull", "NOR": "McLaren"}
        signals = _mine_sprint_vs_race_pace(db, [sprint, race], dc_map)
        assert len(signals) == 1
        assert signals[0].subject == "McLaren"
        assert signals[0].signal_type == "sprint_race_pace_delta"
        assert signals[0].source_refs[0]["delta_s"] == 1.0 - 3.0
