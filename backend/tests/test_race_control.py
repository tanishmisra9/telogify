from sqlmodel import select

from telogify.ingest.race_control import parse_race_control


def _msgs(*pairs):
    return [{"Lap": lap, "Message": msg} for lap, msg in pairs]


def test_collision_yields_one_event_per_car():
    ev = parse_race_control(_msgs((57, "TURN 1 INCIDENT INVOLVING CARS 3 (VER) AND 63 (RUS) NOTED - CAUSING A COLLISION")))
    assert {(e.driver, e.kind) for e in ev} == {("VER", "collision"), ("RUS", "collision")}
    assert all(e.lap == 57 for e in ev)


def test_penalty_and_safety_car():
    ev = parse_race_control(_msgs(
        (30, "FIA STEWARDS: DRIVE THROUGH PENALTY FOR CAR 77 (BOT) - SPEEDING IN THE PIT LANE"),
        (12, "SAFETY CAR DEPLOYED"),
    ))
    kinds = {(e.driver, e.kind) for e in ev}
    assert ("BOT", "penalty") in kinds
    assert (None, "safety_car") in kinds  # track-wide event, no driver


def test_drops_procedural_noise_and_deletions():
    ev = parse_race_control(_msgs(
        (4, "FIA STEWARDS: TURN 11 INCIDENT INVOLVING CARS 43 (COL) AND 44 (HAM) REVIEWED NO FURTHER INVESTIGATION"),
        (20, "FIA STEWARDS: INCIDENT INVOLVING CAR 3 (VER) WILL BE INVESTIGATED AFTER THE RACE"),
        (57, "CAR 16 (LEC) TIME 1:49.834 DELETED - TRACK LIMITS AT TURN 8"),
        (5, "GREEN LIGHT - PIT EXIT OPEN"),
    ))
    assert ev == []


def test_incident_kept_but_investigation_dropped():
    ev = parse_race_control(_msgs(
        (16, "INCIDENT INVOLVING CAR 3 (VER) NOTED - FAILING TO FOLLOW RACE DIRECTORS INSTRUCTIONS"),
        (20, "FIA STEWARDS: INCIDENT INVOLVING CAR 3 (VER) WILL BE INVESTIGATED AFTER THE RACE"),
    ))
    assert [(e.driver, e.kind) for e in ev] == [("VER", "incident")]


def test_retirement_and_forced_off():
    ev = parse_race_control(_msgs(
        (42, "CAR 14 (ALO) STOPPED ON TRACK"),
        (18, "TURN 4 INCIDENT INVOLVING CAR 55 (SAI) NOTED - FORCING ANOTHER DRIVER OFF"),
    ))
    kinds = {(e.driver, e.kind) for e in ev}
    assert ("ALO", "retirement") in kinds
    assert ("SAI", "forced_off") in kinds


def test_dedupes_repeated_car_in_same_message():
    msg = "TURN 1 INCIDENT INVOLVING CARS 3 (VER) AND 63 (RUS) NOTED - CAUSING A COLLISION"
    ev = parse_race_control(_msgs((57, msg)) + _msgs((57, msg)))
    assert len(ev) == 2  # one row per car, not duplicated when message repeats


def test_skips_empty_messages_and_blank_laps():
    ev = parse_race_control([
        {"Lap": None, "Message": ""},
        {"Lap": "  ", "Message": "SAFETY CAR DEPLOYED"},
    ])
    assert len(ev) == 1 and ev[0].kind == "safety_car" and ev[0].lap is None


def test_unparseable_lap_value_falls_back_to_none():
    ev = parse_race_control([{"Lap": "not-a-number", "Message": "SAFETY CAR DEPLOYED"}])
    assert len(ev) == 1 and ev[0].lap is None


# --- store_race_control: DB orchestration -----------------------------------


def test_store_race_control_persists_events_and_skips_non_race_sessions(db_session):
    import pandas as pd

    from telogify.ingest.loader import WeekendData
    from telogify.ingest.race_control import store_race_control
    from telogify.models import RaceControlEvent, RaceWeekend, Session as SessionRow

    wk = RaceWeekend(year=2068, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    race = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
    db_session.add(race)
    db_session.commit()
    db_session.refresh(race)

    class _FakeSession:
        def __init__(self, messages):
            self.race_control_messages = pd.DataFrame(messages)

    race_session = _FakeSession([{"Lap": 19, "Message": "COLLISION (VER) AND (GAS)"}])
    # Q isn't a race/sprint session -> skipped entirely without touching race_control_messages
    quali_session = _FakeSession([{"Lap": 1, "Message": "COLLISION (LEC) AND (HAM)"}])

    data = WeekendData(weekend=wk, sessions={"R": race_session, "Q": quali_session})
    store_race_control(data, db_session)

    stored = db_session.exec(select(RaceControlEvent).where(RaceControlEvent.session_id == race.id)).all()
    assert {e.driver for e in stored} == {"VER", "GAS"}

    # idempotent re-run (delete + reinsert) leaves exactly two rows, not duplicates
    store_race_control(data, db_session)
    stored_again = db_session.exec(select(RaceControlEvent).where(RaceControlEvent.session_id == race.id)).all()
    assert len(stored_again) == 2


def test_store_race_control_handles_missing_race_control_messages(db_session):
    from telogify.ingest.loader import WeekendData
    from telogify.ingest.race_control import store_race_control
    from telogify.models import RaceControlEvent, RaceWeekend, Session as SessionRow

    wk = RaceWeekend(year=2067, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    race = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
    db_session.add(race)
    db_session.commit()
    db_session.refresh(race)

    # a session object with no race_control_messages attribute -> AttributeError caught, records=[]
    # "SPRINT" is a race session type but has no matching DB Session row -> skipped
    data = WeekendData(weekend=wk, sessions={"R": object(), "SPRINT": object()})
    store_race_control(data, db_session)

    stored = db_session.exec(select(RaceControlEvent).where(RaceControlEvent.session_id == race.id)).all()
    assert stored == []
