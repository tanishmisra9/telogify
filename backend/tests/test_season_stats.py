from telogify.analysis.season_stats import build_season_stats
from telogify.models import RaceWeekend, Session as SessionRow, Stint


def test_build_season_stats_returns_none_when_year_has_no_weekends(db_session):
    assert build_season_stats(2025, db_session) is None


def test_build_season_stats_sums_laps_and_km_for_known_circuit(db_session):
    wk = RaceWeekend(year=2025, round=8, circuit_name="Monte Carlo", country="Monaco", event_name="Monaco GP")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)

    race = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
    db_session.add(race)
    db_session.commit()
    db_session.refresh(race)

    db_session.add_all(
        [
            Stint(session_id=race.id, driver="LEC", stint_number=1, lap_times_json=[90.1, 90.2, 90.3]),
            Stint(session_id=race.id, driver="LEC", stint_number=2, lap_times_json=[90.4, 90.5]),
        ]
    )
    db_session.commit()

    out = build_season_stats(2025, db_session)

    # Monte Carlo is 3.337 km; 5 laps total across the two stints.
    assert out == {"year": 2025, "total_laps": 5, "total_km": round(5 * 3.337, 1)}


def test_build_season_stats_counts_laps_but_not_km_for_unknown_circuit(db_session):
    wk = RaceWeekend(year=2025, round=99, circuit_name="Nowhere Speedway", country="Nowhere", event_name="Nowhere GP")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)

    race = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
    db_session.add(race)
    db_session.commit()
    db_session.refresh(race)

    db_session.add(Stint(session_id=race.id, driver="HAM", stint_number=1, lap_times_json=[91.0, 91.1]))
    db_session.commit()

    out = build_season_stats(2025, db_session)

    assert out == {"year": 2025, "total_laps": 2, "total_km": 0.0}


def test_build_season_stats_sums_across_multiple_weekends_same_year(db_session):
    wk1 = RaceWeekend(year=2025, round=1, circuit_name="Melbourne", country="Australia", event_name="Australian GP")
    wk2 = RaceWeekend(year=2025, round=2, circuit_name="Shanghai", country="China", event_name="Chinese GP")
    db_session.add_all([wk1, wk2])
    db_session.commit()
    db_session.refresh(wk1)
    db_session.refresh(wk2)

    race1 = SessionRow(weekend_id=wk1.id, session_type="R", status="loaded")
    race2 = SessionRow(weekend_id=wk2.id, session_type="R", status="loaded")
    db_session.add_all([race1, race2])
    db_session.commit()
    db_session.refresh(race1)
    db_session.refresh(race2)

    db_session.add(Stint(session_id=race1.id, driver="VER", stint_number=1, lap_times_json=[80.0, 80.1]))
    db_session.add(Stint(session_id=race2.id, driver="VER", stint_number=1, lap_times_json=[95.0]))
    db_session.commit()

    out = build_season_stats(2025, db_session)

    expected_km = round(2 * 5.278 + 1 * 5.451, 1)
    assert out == {"year": 2025, "total_laps": 3, "total_km": expected_km}
