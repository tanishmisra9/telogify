from sqlmodel import select

from telogify.analysis.attribution import (
    DriverCorner,
    aggregate_driver_corner,
    attribute_corner,
    classify_speed,
    store_attributions,
)


# --- Rule 1: confidence-weighted mean (not sum) ---
def test_aggregate_is_lap_weighted_mean():
    metric, total = aggregate_driver_corner([(200.0, 5), (210.0, 15)])
    assert total == 20
    assert abs(metric - 207.5) < 1e-9  # (200*5 + 210*15) / 20, not a sum


# --- Rule 2: low-sample capping ---
def test_aggregate_excludes_thin_compound():
    metric, total = aggregate_driver_corner([(150.0, 3), (200.0, 10)])
    assert total == 10  # the 3-lap compound dropped
    assert metric == 200.0


def test_aggregate_all_thin_returns_none():
    assert aggregate_driver_corner([(150.0, 2), (160.0, 4)]) is None


# --- car vs driver split ---
def test_car_dominated_split():
    a = [DriverCorner("McLaren", "NOR", 210.0, 8), DriverCorner("McLaren", "PIA", 208.0, 8)]
    b = [DriverCorner("Ferrari", "LEC", 200.0, 8), DriverCorner("Ferrari", "HAM", 198.0, 8)]
    attr = attribute_corner(7, a, b)

    assert abs(attr.delta_s - 10.0) < 1e-9  # car_a 209 - car_b 199
    assert attr.car_pct > attr.driver_pct  # 10 km/h gap dwarfs 2 km/h teammate spread
    assert attr.confidence == 1.0  # both teams two strong drivers


# --- Rule 3: teammate reliability caps confidence ---
def test_single_driver_team_caps_confidence():
    a = [DriverCorner("Williams", "ALB", 210.0, 8)]  # only one driver
    b = [DriverCorner("Ferrari", "LEC", 200.0, 8), DriverCorner("Ferrari", "HAM", 198.0, 8)]
    attr = attribute_corner(7, a, b)
    assert attr.confidence == 0.5  # 1.0 base * teammate cap


def test_weak_teammate_baseline_caps_confidence():
    # one driver under the 60% baseline (4/8 = 0.5) -> team unreliable, and min_laps drives base conf
    a = [DriverCorner("RB", "VER", 210.0, 8), DriverCorner("RB", "LAW", 208.0, 4)]
    b = [DriverCorner("Ferrari", "LEC", 200.0, 8), DriverCorner("Ferrari", "HAM", 198.0, 8)]
    attr = attribute_corner(7, a, b)
    assert attr.confidence == 0.25  # base 4/8=0.5 * cap 0.5


def test_attribute_corner_returns_none_without_two_constructors():
    a = [DriverCorner("Ferrari", "LEC", 210.0, 8)]
    assert attribute_corner(1, a, []) is None
    assert attribute_corner(1, [], []) is None


def test_classify_speed_bands():
    from telogify.analysis.attribution import LOW_MAX_KMH, MID_MAX_KMH

    assert classify_speed(LOW_MAX_KMH - 0.1) == "low"
    assert classify_speed(LOW_MAX_KMH) == "mid"
    assert classify_speed(MID_MAX_KMH - 0.1) == "mid"
    assert classify_speed(MID_MAX_KMH) == "high"
    assert classify_speed(250.0) == "high"


def test_driver_confidence_scales_to_target_laps():
    from telogify.analysis.attribution import TARGET_LAPS, driver_confidence

    assert driver_confidence(0) == 0.0
    assert driver_confidence(TARGET_LAPS // 2) == 0.5
    assert driver_confidence(TARGET_LAPS) == 1.0
    assert driver_confidence(TARGET_LAPS + 5) == 1.0


# --- DB-side orchestration --------------------------------------------------


def test_store_attributions_persists_pairwise_corner_deltas(db_session):
    from telogify.models import Attribution, Fingerprint, RaceWeekend, Session as SessionRow, SessionResult

    wk = RaceWeekend(year=2072, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    session = SessionRow(weekend_id=wk.id, session_type="FP1", status="loaded")
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)

    db_session.add_all(
        [
            SessionResult(session_id=session.id, driver="LEC", constructor="Ferrari", position=1),
            SessionResult(session_id=session.id, driver="HAM", constructor="Ferrari", position=2),
            SessionResult(session_id=session.id, driver="VER", constructor="Red Bull", position=3),
            SessionResult(session_id=session.id, driver="PER", constructor="Red Bull", position=4),
            # NOR has fingerprints but no SessionResult row -> no constructor mapping, excluded
        ]
    )
    db_session.add_all(
        [
            Fingerprint(session_id=session.id, driver="LEC", corner_number=1, min_speed=200.0, clean_lap_count=8),
            Fingerprint(session_id=session.id, driver="HAM", corner_number=1, min_speed=198.0, clean_lap_count=8),
            Fingerprint(session_id=session.id, driver="VER", corner_number=1, min_speed=210.0, clean_lap_count=8),
            Fingerprint(session_id=session.id, driver="PER", corner_number=1, min_speed=208.0, clean_lap_count=8),
            # thin sample (< MIN_CLEAN_LAPS) at corner 2 -> aggregate_driver_corner drops it
            Fingerprint(session_id=session.id, driver="LEC", corner_number=2, min_speed=150.0, clean_lap_count=2),
            Fingerprint(session_id=session.id, driver="NOR", corner_number=1, min_speed=205.0, clean_lap_count=8),
        ]
    )
    db_session.commit()

    store_attributions(wk.id, db_session)

    stored = db_session.exec(
        select(Attribution).where(Attribution.session_id == session.id)
    ).all()
    assert len(stored) == 1  # only corner 1 has 2+ constructors with a valid aggregate
    assert stored[0].corner_number == 1
    assert {stored[0].constructor_a, stored[0].constructor_b} == {"Ferrari", "Red Bull"}

    # idempotent re-run (delete + reinsert) leaves exactly one row, not a duplicate
    store_attributions(wk.id, db_session)
    stored_again = db_session.exec(
        select(Attribution).where(Attribution.session_id == session.id)
    ).all()
    assert len(stored_again) == 1
