"""Tests for candidate miner caps (corner/straight delta filters). Uses test DB, no FastF1."""

from sqlmodel import Session

from telogify.analysis.candidates import (
    MAX_CORNER_DELTA_KMH,
    MAX_STRAIGHT_DEFICIT_KMH,
    _mine_corner_deltas,
    _mine_straight_deltas,
)
from telogify.models import Attribution, RaceWeekend, Session as SessionRow, StraightSegment


def test_corner_delta_cap_filters_at_boundary(test_engine):
    with Session(test_engine) as db:
        wk = RaceWeekend(year=2026, round=99, circuit_name="X", country="Y", event_name="Cap Test")
        db.add(wk)
        db.commit()
        db.refresh(wk)

        sess = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
        db.add(sess)
        db.commit()
        db.refresh(sess)

        # Just inside cap: kept. Just outside: dropped.
        db.add(Attribution(
            session_id=sess.id, corner_number=1, constructor_a="Red Bull", constructor_b="Ferrari",
            delta_s=MAX_CORNER_DELTA_KMH, confidence=0.9,
        ))
        db.add(Attribution(
            session_id=sess.id, corner_number=2, constructor_a="McLaren", constructor_b="Mercedes",
            delta_s=MAX_CORNER_DELTA_KMH + 0.1, confidence=0.9,
        ))
        db.commit()

        signals = _mine_corner_deltas(db, [sess])
        assert len(signals) == 1
        assert signals[0].magnitude == MAX_CORNER_DELTA_KMH
        assert signals[0].locus == "corner:1"


def test_corner_delta_negative_delta_attributes_slower_constructor(test_engine):
    with Session(test_engine) as db:
        wk = RaceWeekend(year=2026, round=97, circuit_name="X", country="Y", event_name="Sign Test")
        db.add(wk)
        db.commit()
        db.refresh(wk)

        sess = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
        db.add(sess)
        db.commit()
        db.refresh(sess)

        db.add(Attribution(
            session_id=sess.id, corner_number=3, constructor_a="Ferrari", constructor_b="McLaren",
            delta_s=-10.0, confidence=0.8,
        ))
        db.commit()

        signals = _mine_corner_deltas(db, [sess])
        assert len(signals) == 1
        assert signals[0].subject == "Ferrari"  # negative delta -> constructor_a is slower
        assert signals[0].magnitude == 10.0


def test_straight_deficit_cap_filters_at_boundary(test_engine):
    with Session(test_engine) as db:
        wk = RaceWeekend(year=2026, round=98, circuit_name="X", country="Y", event_name="Straight Cap")
        db.add(wk)
        db.commit()
        db.refresh(wk)

        sess = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
        db.add(sess)
        db.commit()
        db.refresh(sess)

        # Field tops 300 km/h; leader 320, one deficit at cap and one above cap.
        db.add(StraightSegment(session_id=sess.id, driver="VER", drs_zone_id=1, max_speed_kmh=320.0))
        db.add(StraightSegment(
            session_id=sess.id, driver="NOR", drs_zone_id=1,
            max_speed_kmh=320.0 - MAX_STRAIGHT_DEFICIT_KMH,
        ))
        db.add(StraightSegment(
            session_id=sess.id, driver="LEC", drs_zone_id=1,
            max_speed_kmh=320.0 - MAX_STRAIGHT_DEFICIT_KMH - 1.0,
        ))
        db.commit()

        dc_map = {"VER": "Red Bull", "NOR": "McLaren", "LEC": "Ferrari"}
        signals = _mine_straight_deltas(db, [sess], dc_map)
        assert len(signals) == 1
        assert signals[0].subject == "McLaren"
        assert signals[0].magnitude == MAX_STRAIGHT_DEFICIT_KMH
