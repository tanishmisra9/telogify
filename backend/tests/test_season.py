"""Tests for the season-rollup pure functions (aggregate, overall_ranking, confidence) plus
the build_season_snapshot / build_season_accel_scatter DB orchestrators below."""

import pytest

from telogify.analysis.season import (
    _reference_compound,
    _stride_cap,
    _tyre_deg_on_ref,
    aggregate,
    build_season_accel_scatter,
    build_season_snapshot,
    confidence,
    overall_ranking,
)


# --- _stride_cap -----------------------------------------------------------


def test_stride_cap_below_limit_is_unchanged():
    assert _stride_cap([1, 2, 3], 10) == [1, 2, 3]


def test_stride_cap_at_limit_is_unchanged():
    assert _stride_cap(list(range(10)), 10) == list(range(10))


def test_stride_cap_thins_evenly_and_keeps_order():
    result = _stride_cap(list(range(21)), 10)
    assert result == list(range(0, 21, 3))
    assert len(result) <= 10


def test_stride_cap_empty():
    assert _stride_cap([], 10) == []


# --- aggregate -----------------------------------------------------------


def test_aggregate_empty():
    assert aggregate([]) == {"mean": None, "spread": None, "n": 0}
    assert aggregate([None, None]) == {"mean": None, "spread": None, "n": 0}


def test_aggregate_single_round_has_zero_spread():
    a = aggregate([0.5])
    assert a["mean"] == 0.5
    assert a["spread"] == 0.0
    assert a["n"] == 1


def test_aggregate_spread_separates_consistent_from_swingy():
    consistent = aggregate([0.4, 0.5, 0.6])  # mean 0.5, tight
    swingy = aggregate([0.0, 0.5, 1.0])  # same mean 0.5, wide
    assert consistent["mean"] == swingy["mean"] == 0.5
    assert swingy["spread"] > consistent["spread"]


def test_aggregate_ignores_none_but_counts_the_rest():
    a = aggregate([1.0, None, 3.0])
    assert a["n"] == 2
    assert a["mean"] == 2.0


# --- overall_ranking -----------------------------------------------------


def test_overall_ranking_blend_orders_by_weighted_deficit():
    # A: best race, worst quali. B: worst race, best quali. With 0.6/0.4, race wins the tie.
    pace = {"A": 0.0, "B": 1.0}
    quali = {"A": 1.0, "B": 0.0}
    ranking = overall_ranking(pace, quali)
    # A score = 0.6*0 + 0.4*1 = 0.4; B score = 0.6*1 + 0.4*0 = 0.6 -> A ranks first.
    assert ranking["A"]["rank"] == 1
    assert ranking["B"]["rank"] == 2
    assert ranking["A"]["score"] < ranking["B"]["score"]


def test_overall_ranking_fastest_race_and_quali_ranks_first():
    pace = {"A": 0.0, "B": 0.5, "C": 1.2}
    quali = {"A": 0.0, "B": 0.3, "C": 0.9}
    ranking = overall_ranking(pace, quali)
    assert ranking["A"]["rank"] == 1
    assert ranking["C"]["rank"] == 3


def test_overall_ranking_team_missing_quali_scored_on_race_alone():
    pace = {"A": 0.0, "B": 1.0}
    quali = {"A": 0.0}  # B has no quali data
    ranking = overall_ranking(pace, quali)
    assert set(ranking) == {"A", "B"}
    assert ranking["A"]["rank"] == 1  # A still fastest, not sunk by B's missing metric


def test_overall_ranking_empty():
    assert overall_ranking({}, {}) == {}


# --- confidence ----------------------------------------------------------


def test_confidence_full_season_is_high():
    assert confidence(9, 10) == "high"


def test_confidence_partial_is_med():
    assert confidence(5, 10) == "med"


def test_confidence_sparse_is_low():
    assert confidence(2, 10) == "low"
    assert confidence(0, 10) == "low"
    assert confidence(1, 0) == "low"


# --- tyre wear on a reference compound -----------------------------------


def test_reference_compound_is_the_most_run_by_laps():
    deg = {
        "A": [("MEDIUM", 0.05, 30), ("SOFT", 0.2, 6)],
        "B": [("MEDIUM", 0.06, 25), ("HARD", 0.04, 20)],
    }
    # MEDIUM: 55 laps, HARD: 20, SOFT: 6 -> MEDIUM
    assert _reference_compound(deg) == "MEDIUM"


def test_reference_compound_empty_is_none():
    assert _reference_compound({}) is None


def test_tyre_deg_uses_only_the_reference_compound():
    # A short 6-lap SOFT outlier at -2.7 must not touch the MEDIUM-based number.
    fits = [("MEDIUM", 0.05, 30), ("MEDIUM", 0.07, 28), ("SOFT", -2.7, 6)]
    assert _tyre_deg_on_ref(fits, "MEDIUM") == pytest.approx(0.06)  # median(0.05, 0.07)


def test_tyre_deg_falls_back_when_no_reference_compound_run():
    fits = [("HARD", 0.10, 20), ("HARD", 0.12, 18)]
    assert _tyre_deg_on_ref(fits, "MEDIUM") == pytest.approx(0.11)  # pooled median fallback


def test_tyre_deg_empty_is_none():
    assert _tyre_deg_on_ref([], "MEDIUM") is None


# --- build_season_snapshot: DB orchestration --------------------------------


def test_build_season_snapshot_none_for_unseen_year(db_session):
    assert build_season_snapshot(2049, db_session) is None


def test_build_season_snapshot_rolls_up_race_and_quali_across_rounds(db_session):
    from telogify.models import (
        QualiCharacter,
        RaceWeekend,
        SectorBest,
        Session as SessionRow,
        SessionResult,
        Stint,
    )

    year = 2050
    wk1 = RaceWeekend(year=year, round=1, circuit_name="X", country="Y", event_name="R1")
    wk2 = RaceWeekend(year=year, round=2, circuit_name="X", country="Y", event_name="R2")
    db_session.add(wk1)
    db_session.add(wk2)
    db_session.commit()
    db_session.refresh(wk1)
    db_session.refresh(wk2)

    race1 = SessionRow(weekend_id=wk1.id, session_type="R", status="loaded")
    q1 = SessionRow(weekend_id=wk1.id, session_type="Q", status="loaded")
    race2 = SessionRow(weekend_id=wk2.id, session_type="R", status="loaded")
    db_session.add(race1)
    db_session.add(q1)
    db_session.add(race2)
    db_session.commit()
    db_session.refresh(race1)
    db_session.refresh(q1)
    db_session.refresh(race2)

    db_session.add_all(
        [
            SessionResult(session_id=q1.id, driver="LEC", constructor="Ferrari", position=1),
            SessionResult(session_id=q1.id, driver="VER", constructor="Red Bull", position=2),
            SessionResult(session_id=race1.id, driver="LEC", constructor="Ferrari", position=1),
            SessionResult(session_id=race1.id, driver="VER", constructor="Red Bull", position=2),
            SessionResult(session_id=race2.id, driver="LEC", constructor="Ferrari", position=1),
            SessionResult(session_id=race2.id, driver="VER", constructor="Red Bull", position=2),
        ]
    )

    ages = [1, 2, 3, 4, 5, 6]
    degrading = [90.0, 90.3, 90.6, 90.9, 91.2, 91.5]
    db_session.add_all(
        [
            Stint(session_id=race1.id, driver="LEC", stint_number=1, lap_start=2, compound="MEDIUM", lap_times_json=degrading, tyre_ages_json=ages),
            Stint(session_id=race1.id, driver="VER", stint_number=1, lap_start=2, compound="MEDIUM", lap_times_json=[89.0] * 6, tyre_ages_json=ages),
            Stint(session_id=race2.id, driver="LEC", stint_number=1, lap_start=2, compound="MEDIUM", lap_times_json=[92.0] * 6),
            Stint(session_id=race2.id, driver="VER", stint_number=1, lap_start=2, compound="MEDIUM", lap_times_json=[90.0] * 6),
        ]
    )
    db_session.add_all(
        [
            QualiCharacter(session_id=q1.id, driver="LEC", constructor="Ferrari", lap_time_s=90.0, top_speed_kmh=320.0),
            QualiCharacter(session_id=q1.id, driver="VER", constructor="Red Bull", lap_time_s=89.0, top_speed_kmh=330.0),
        ]
    )
    db_session.add_all(
        [
            SectorBest(session_id=q1.id, driver="LEC", sector=1, best_time_s=30.0),
            SectorBest(session_id=q1.id, driver="VER", sector=1, best_time_s=29.5),
        ]
    )
    db_session.commit()

    snapshot = build_season_snapshot(year, db_session)

    assert snapshot["year"] == year
    assert [r["round"] for r in snapshot["rounds"]] == [1, 2]
    by_constructor = {r["constructor"]: r for r in snapshot["constructors"]}
    assert set(by_constructor) == {"Ferrari", "Red Bull"}

    red_bull = by_constructor["Red Bull"]
    assert red_bull["overall_rank"] == 1  # faster on both race pace and qualifying
    assert red_bull["pace_gap"]["n"] == 2  # ran both rounds -> full-season confidence
    assert red_bull["confidence"] == "high"
    assert red_bull["sector_dominance_count"] == 1
    assert red_bull["top_speed_deficit_kmh"] == 0.0
    assert len(red_bull["trend"]["pace"]) == 2
    assert len(red_bull["trend"]["cumulative"]) == 2

    ferrari = by_constructor["Ferrari"]
    assert ferrari["tyre_deg_s_per_lap"] is not None and ferrari["tyre_deg_s_per_lap"] > 0
    assert ferrari["quali_gap_pct"]["n"] == 1  # quali data from round 1 only


# --- build_season_accel_scatter: DB orchestration ---------------------------


def test_build_season_accel_scatter_pools_by_constructor_and_skips_gaps(db_session):
    from telogify.models import AccelSample, RaceWeekend, Session as SessionRow

    year = 2051
    wk_race = RaceWeekend(year=year, round=1, circuit_name="X", country="Y", event_name="Z")
    wk_no_race = RaceWeekend(year=year, round=2, circuit_name="X", country="Y", event_name="Z2")
    db_session.add(wk_race)
    db_session.add(wk_no_race)
    db_session.commit()
    db_session.refresh(wk_race)
    db_session.refresh(wk_no_race)

    race = SessionRow(weekend_id=wk_race.id, session_type="R", status="loaded")
    quali = SessionRow(weekend_id=wk_no_race.id, session_type="Q", status="loaded")  # no "R" session for this weekend
    db_session.add(race)
    db_session.add(quali)
    db_session.commit()
    db_session.refresh(race)
    db_session.refresh(quali)

    db_session.add_all(
        [
            AccelSample(session_id=race.id, driver="LEC", constructor="Ferrari", speed_kmh_json=[200.0, 210.0], longitudinal_accel_ms2_json=[1.0, 1.1]),
            AccelSample(session_id=race.id, driver="UNKNOWN", constructor=None, speed_kmh_json=[150.0], longitudinal_accel_ms2_json=[0.5]),
        ]
    )
    db_session.commit()

    scatter = build_season_accel_scatter(year, db_session)
    assert set(scatter) == {"Ferrari"}  # no-constructor sample skipped, no-race weekend skipped
    assert scatter["Ferrari"] == [[200.0, 1.0], [210.0, 1.1]]
