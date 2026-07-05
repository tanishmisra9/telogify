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
