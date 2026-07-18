from telogify.analysis.diagnose import diagnose
from telogify.models import (
    Attribution,
    Fingerprint,
    RaceWeekend,
    SessionResult,
    Session as SessionRow,
)


def test_diagnose_reports_no_weekend_found(db_session):
    out = diagnose(2025, 11, db_session)
    assert out == "No weekend found for 2025 round 11. Run `telogify run-weekend` first."


def test_diagnose_reports_clean_lap_counts_and_mean_confidence(db_session):
    wk = RaceWeekend(year=2025, round=11, circuit_name="Spielberg", country="Austria", event_name="Austrian GP")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)

    race = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
    db_session.add(race)
    db_session.commit()
    db_session.refresh(race)

    db_session.add_all(
        [
            SessionResult(session_id=race.id, position=1, driver="VER", constructor="Red Bull Racing"),
            SessionResult(session_id=race.id, position=2, driver="PER", constructor="Red Bull Racing"),
            SessionResult(session_id=race.id, position=3, driver="LEC", constructor="Ferrari"),
        ]
    )
    db_session.commit()

    # Two drivers, same constructor, same corner: counts must sum across drivers.
    db_session.add_all(
        [
            Fingerprint(session_id=race.id, driver="VER", corner_number=1, clean_lap_count=5),
            Fingerprint(session_id=race.id, driver="PER", corner_number=1, clean_lap_count=3),
            Fingerprint(session_id=race.id, driver="VER", corner_number=2, clean_lap_count=4),
            Fingerprint(session_id=race.id, driver="LEC", corner_number=1, clean_lap_count=7),
        ]
    )
    db_session.commit()

    db_session.add_all(
        [
            Attribution(
                session_id=race.id,
                corner_number=1,
                constructor_a="Red Bull Racing",
                constructor_b="Ferrari",
                confidence=0.8,
            ),
            Attribution(
                session_id=race.id,
                corner_number=1,
                constructor_a="Red Bull Racing",
                constructor_b="Ferrari",
                confidence=0.6,
            ),
        ]
    )
    db_session.commit()

    out = diagnose(2025, 11, db_session)

    assert "Diagnose: Austrian GP (2025 round 11)" in out
    # Red Bull Racing: corner 1 (5+3=8 laps) + corner 2 (4 laps) across 2 corners.
    assert "Red Bull Racing: corners=2 total_clean_laps=12 mean_attr_confidence=0.70" in out
    assert "    T1: clean_laps=8" in out
    assert "    T2: clean_laps=4" in out
    # Ferrari: only corner 1, 7 laps; same two Attribution rows also give it confidence 0.70
    # since confidence is credited to both constructor_a and constructor_b.
    assert "Ferrari: corners=1 total_clean_laps=7 mean_attr_confidence=0.70" in out
    assert "    T1: clean_laps=7" in out


def test_diagnose_reports_no_confidence_as_n_a(db_session):
    wk = RaceWeekend(year=2026, round=1, circuit_name="Melbourne", country="Australia", event_name="Australian GP")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)

    race = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
    db_session.add(race)
    db_session.commit()
    db_session.refresh(race)

    db_session.add(SessionResult(session_id=race.id, position=1, driver="NOR", constructor="McLaren"))
    db_session.commit()
    db_session.add(Fingerprint(session_id=race.id, driver="NOR", corner_number=1, clean_lap_count=2))
    db_session.commit()

    out = diagnose(2026, 1, db_session)

    assert "McLaren: corners=1 total_clean_laps=2 mean_attr_confidence=n/a" in out
