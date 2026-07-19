from sqlmodel import select

from telogify.analysis.constructor_index import (
    CornerScore,
    _race_stints_as_dicts,
    build_constructor_index,
    rank_constructors,
    summarize_constructor,
    weighted_mean,
)
from telogify.analysis.race_pace import constructor_median_gaps


def test_weighted_mean_is_not_a_sum():
    assert weighted_mean([(10.0, 1.0), (20.0, 1.0)]) == 15.0
    assert weighted_mean([]) is None
    assert weighted_mean([(5.0, 0.0)]) is None


def test_more_corners_does_not_inflate_score():
    # Same advantage/confidence, but one constructor is represented at 10x more corners.
    few = [CornerScore("high", 5.0, 1.0)]
    many = [CornerScore("high", 5.0, 1.0)] * 10
    assert summarize_constructor(few)["overall"] == summarize_constructor(many)["overall"] == 5.0


def test_confidence_weights_dominate():
    scores = [CornerScore("mid", 10.0, 0.9), CornerScore("mid", -10.0, 0.1)]
    # high-confidence +10 should pull the mean well above zero
    assert summarize_constructor(scores)["mid"] == (10 * 0.9 - 10 * 0.1) / (0.9 + 0.1)


def test_summarize_constructor_empty_scores():
    assert summarize_constructor([]) == {"high": None, "mid": None, "low": None, "overall": None}
    ranks = rank_constructors({"McLaren": 4.0, "Ferrari": 1.0, "Sauber": None})
    assert ranks["McLaren"] == 1
    assert ranks["Ferrari"] == 2
    assert ranks["Sauber"] == 3  # no score -> last, not buried by a sparsity bug


def test_constructor_median_gaps_relative_to_fastest():
    """constructor_median_gaps replaces lap_deficits as the canonical ranking metric."""
    stints = [
        {"driver": "VER", "constructor": "Red Bull", "compound": "MEDIUM", "lap_times": [90.0, 90.1, 90.2]},
        {"driver": "LEC", "constructor": "Ferrari", "compound": "MEDIUM", "lap_times": [90.3, 90.4, 90.5]},
        {"driver": "RUS", "constructor": "Mercedes", "compound": "HARD",   "lap_times": [91.0, 91.1, 91.2]},
    ]
    gaps = constructor_median_gaps(stints)
    assert gaps["Red Bull"] == 0.0
    assert abs(gaps["Ferrari"] - 0.3) < 1e-9
    assert abs(gaps["Mercedes"] - 1.0) < 1e-9


# --- DB-side orchestration --------------------------------------------------


def test_race_stints_as_dicts_empty_without_a_race_session(db_session):
    from telogify.models import RaceWeekend, Session as SessionRow

    wk = RaceWeekend(year=2071, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    fp1 = SessionRow(weekend_id=wk.id, session_type="FP1", status="loaded")
    db_session.add(fp1)
    db_session.commit()
    db_session.refresh(fp1)

    assert _race_stints_as_dicts(db_session, [fp1], {}) == []


def test_build_constructor_index_ranks_by_race_pace_and_persists_corner_scores(db_session):
    from telogify.models import ConstructorIndex, Fingerprint, RaceWeekend, Session as SessionRow, SessionResult, Stint

    wk = RaceWeekend(year=2070, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    fp1 = SessionRow(weekend_id=wk.id, session_type="FP1", status="loaded")
    race = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
    db_session.add(fp1)
    db_session.add(race)
    db_session.commit()
    db_session.refresh(fp1)
    db_session.refresh(race)

    db_session.add_all(
        [
            SessionResult(session_id=fp1.id, driver="LEC", constructor="Ferrari", position=1),
            SessionResult(session_id=fp1.id, driver="VER", constructor="Red Bull", position=2),
        ]
    )
    db_session.add_all(
        [
            # corner 1: both constructors represented -> a real field to measure advantage against
            Fingerprint(session_id=fp1.id, driver="LEC", corner_number=1, min_speed=200.0, clean_lap_count=8),
            Fingerprint(session_id=fp1.id, driver="VER", corner_number=1, min_speed=210.0, clean_lap_count=8),
            # corner 2: only Ferrari present -> len(by_constructor) < 2, skipped
            Fingerprint(session_id=fp1.id, driver="LEC", corner_number=2, min_speed=150.0, clean_lap_count=8),
        ]
    )
    db_session.add_all(
        [
            Stint(session_id=race.id, driver="VER", stint_number=1, lap_start=2, compound="SOFT", lap_times_json=[90.0] * 6),
            Stint(session_id=race.id, driver="LEC", stint_number=1, lap_start=2, compound="SOFT", lap_times_json=[91.0] * 6),
        ]
    )
    db_session.commit()

    build_constructor_index(wk.id, db_session)

    rows = {
        r.constructor: r
        for r in db_session.exec(
            select(ConstructorIndex).where(ConstructorIndex.weekend_id == wk.id)
        ).all()
    }
    assert set(rows) == {"Ferrari", "Red Bull"}
    # Red Bull ran the faster race pace -> ranked ahead despite Ferrari's corner-1 disadvantage
    assert rows["Red Bull"].overall_rank == 1
    assert rows["Ferrari"].overall_rank == 2
    assert rows["Red Bull"].lap_deficit_s == 0.0
    assert rows["Ferrari"].lap_deficit_s > 0.0
    # corner 1 gave Red Bull a positive high-speed advantage over the field mean
    assert rows["Red Bull"].high_score > 0.0

    # idempotent re-run (delete + reinsert) leaves exactly two rows, not duplicates
    build_constructor_index(wk.id, db_session)
    rows_again = db_session.exec(
        select(ConstructorIndex).where(ConstructorIndex.weekend_id == wk.id)
    ).all()
    assert len(rows_again) == 2
