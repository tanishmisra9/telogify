import pytest
from sqlmodel import select

from telogify.analysis.candidates import (
    EXPECTATION_FLOOR,
    OBVIOUSNESS_DISCOUNT,
    Signal,
    _mine_clean_air_pace,
    compute_candidates,
    correlate,
    expectation_factors,
    linear_regression,
    normalize_and_score,
    rank,
)


def _sig(stype, mag, conf, subject, category=None):
    return Signal(
        signal_type=stype,
        category=category or stype,
        magnitude=mag,
        confidence=conf,
        subject=subject,
    )


def test_robustness_normalized_per_signal_type():
    signals = [
        _sig("corner_delta", 10.0, 1.0, "A"),
        _sig("corner_delta", 5.0, 1.0, "B"),
        _sig("straight_delta", 20.0, 0.5, "C"),  # different units, normalized within its own type
    ]
    normalize_and_score(signals)
    by_type = {s.subject: s.robustness for s in signals}
    assert by_type["A"] == 1.0  # peak of corner_delta
    assert by_type["B"] == 0.5
    assert by_type["C"] == 0.5  # 20/20 * 0.5; not dwarfed by the larger raw corner number


def test_correlation_merges_and_outranks_parts():
    straight = _sig("straight_delta", 12.0, 1.0, "Ferrari")
    swing = _sig("position_swing", 2.0, 1.0, "Ferrari")
    lone = _sig("corner_delta", 8.0, 1.0, "McLaren")
    signals = [straight, swing, lone]
    normalize_and_score(signals)

    merged = correlate(signals)
    combined = next(s for s in merged if s.signal_type == "cross_session")

    assert combined.subject == "Ferrari"
    assert combined.robustness > straight.robustness
    assert combined.robustness > swing.robustness
    # the lone, uncorrelated signal survives unchanged
    assert any(s.signal_type == "corner_delta" for s in merged)
    # the two parts are gone, replaced by the single combined candidate
    assert not any(s.signal_type in ("straight_delta", "position_swing") for s in merged)


def test_no_correlation_without_both_signal_types():
    straight = _sig("straight_delta", 12.0, 1.0, "Williams")
    normalize_and_score([straight])
    merged = correlate([straight])
    assert len(merged) == 1 and merged[0].signal_type == "straight_delta"


def test_results_table_finding_is_discounted():
    # a lone position swing (readable from the results table) is halved; a telemetry
    # finding of equal raw strength keeps its full score and outranks it.
    swing = _sig("position_swing", 4.0, 1.0, "Haas", category="result")
    telemetry = _sig("straight_delta", 20.0, 1.0, "Sauber")
    normalize_and_score([swing, telemetry])
    assert swing.robustness == OBVIOUSNESS_DISCOUNT  # 1.0 * 0.5
    assert telemetry.robustness == 1.0


def test_more_channels_outrank_fewer():
    # a three-channel structural read beats a two-channel one for a different team.
    three = [
        _sig("quali_top_speed_delta", 10.0, 1.0, "Ferrari", category="quali_character"),
        _sig("sector_delta", 0.3, 1.0, "Ferrari", category="sector"),
        _sig("tyre_degradation", 1.2, 1.0, "Ferrari", category="degradation"),
    ]
    two = [
        _sig("quali_top_speed_delta", 10.0, 1.0, "Alpine", category="quali_character"),
        _sig("sector_delta", 0.3, 1.0, "Alpine", category="sector"),
    ]
    signals = three + two
    normalize_and_score(signals)
    ranked = [s for s in rank(correlate(signals)) if s.signal_type == "cross_session"]
    # both subjects merged into cross-channel candidates; the three-channel read ranks first
    assert [s.subject for s in ranked] == ["Ferrari", "Alpine"]
    assert ranked[0].robustness > ranked[1].robustness


def test_expectation_factors_reward_over_and_under_delivery():
    # expected order (season pace) vs actual finish for a 6-team field.
    expected = {"Front": 1, "Mid": 4, "Over": 6, "AsExpected": 5, "Absent": 3}
    actual = {"Front": 5, "Mid": 4, "Over": 1, "AsExpected": 5}  # ranks 1..4 among finishers
    f = expectation_factors(expected, actual)
    # overdeliverer (6 -> 1) and front-team underdeliverer (1 -> 5) both near the top
    assert f["Over"] > 0.8 and f["Front"] > 0.8
    # finished right where its pace ranks it -> damped to the floor
    assert f["AsExpected"] == EXPECTATION_FLOOR
    # a team in only one ordering gets no factor (caller treats it as neutral)
    assert "Absent" not in f


def test_expectation_factor_damps_as_expected_below_overdeliverer():
    as_expected = _sig("straight_delta", 20.0, 1.0, "Backmarker")  # biggest raw gap
    over = _sig("straight_delta", 10.0, 1.0, "Haas")  # half the raw gap
    signals = [as_expected, over]
    normalize_and_score(signals, {"Backmarker": EXPECTATION_FLOOR, "Haas": 1.0})
    assert over.robustness > as_expected.robustness  # story beats raw magnitude
    # no map -> unchanged, magnitude wins (guards the default path)
    normalize_and_score(signals)
    assert as_expected.robustness > over.robustness


def test_rank_is_robustness_descending():
    a = _sig("x", 1.0, 1.0, "A")
    a.robustness = 0.2
    b = _sig("y", 1.0, 1.0, "B")
    b.robustness = 0.9
    assert [s.subject for s in rank([a, b])] == ["B", "A"]


def test_linear_regression_recovers_known_line():
    xs = [300.0, 310.0, 320.0, 330.0]
    ys = [90.0, 89.0, 88.0, 87.0]  # exact line: y = -0.1x + 120
    fit = linear_regression(xs, ys)
    assert fit is not None
    slope, intercept = fit
    assert slope == pytest.approx(-0.1)
    assert intercept == pytest.approx(120.0)


def test_linear_regression_none_without_x_spread():
    assert linear_regression([300.0, 300.0, 300.0], [90.0, 89.0, 91.0]) is None


def test_linear_regression_none_with_fewer_than_two_points():
    assert linear_regression([300.0], [90.0]) is None


def test_mine_deployment_excludes_deficits_at_or_below_the_weak_cluster_bar(db_session):
    from telogify.analysis.candidates import _mine_deployment
    from telogify.models import DeploymentTrace, RaceWeekend, Session as SessionRow

    wk = RaceWeekend(year=2026, round=9, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    quali = SessionRow(weekend_id=wk.id, session_type="Q", status="loaded")
    db_session.add(quali)
    db_session.commit()
    db_session.refresh(quali)

    # All three constructors clip on both cars (the consistency gate needs >=2 clippers per
    # team). Ferrari is the field's best (min=40). Williams (min=55) is only 15m behind Ferrari,
    # normal field behaviour; McLaren (min=150) is 110m behind, a genuine deficit.
    rows = [
        DeploymentTrace(session_id=quali.id, driver="LEC", constructor="Ferrari", total_clip_m=40.0, max_clip_m=40.0),
        DeploymentTrace(session_id=quali.id, driver="HAM", constructor="Ferrari", total_clip_m=45.0, max_clip_m=45.0),
        DeploymentTrace(session_id=quali.id, driver="ALB", constructor="Williams", total_clip_m=55.0, max_clip_m=55.0),
        DeploymentTrace(session_id=quali.id, driver="SAI", constructor="Williams", total_clip_m=60.0, max_clip_m=60.0),
        DeploymentTrace(session_id=quali.id, driver="NOR", constructor="McLaren", total_clip_m=150.0, max_clip_m=150.0),
        DeploymentTrace(session_id=quali.id, driver="PIA", constructor="McLaren", total_clip_m=160.0, max_clip_m=160.0),
    ]
    for r in rows:
        db_session.add(r)
    db_session.commit()

    signals = _mine_deployment(db_session, [quali])
    subjects = {s.subject for s in signals}
    assert subjects == {"McLaren"}


def test_expected_ranks_caches_season_snapshot_per_year(db_session, monkeypatch):
    # run_insights_season's parallel workers each call _expected_ranks once per round, and
    # build_season_snapshot scans every ingested round of the year; without the memo, every
    # round redundantly rebuilds the identical whole-season rollup.
    from telogify.analysis import candidates as candidates_module
    from telogify.models import RaceWeekend

    year = 2099  # distinctive test-only year, won't collide with other fixtures' years
    candidates_module._SEASON_SNAPSHOT_CACHE.pop(year, None)

    wk = RaceWeekend(year=year, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)

    calls: list[int] = []

    def fake_snapshot(y, db):
        calls.append(y)
        return {"constructors": [{"constructor": "Ferrari", "overall_rank": 1}]}

    monkeypatch.setattr(candidates_module, "build_season_snapshot", fake_snapshot)

    try:
        first = candidates_module._expected_ranks(wk.id, db_session)
        second = candidates_module._expected_ranks(wk.id, db_session)

        assert first == {"Ferrari": 1}
        assert second == {"Ferrari": 1}
        assert len(calls) == 1  # second lookup reused the cached snapshot, no rebuild
    finally:
        candidates_module._SEASON_SNAPSHOT_CACHE.pop(year, None)


# --- _mine_clean_air_pace ---------------------------------------------------


def _seed_weekend(db_session, year):
    from telogify.models import RaceWeekend, Session as SessionRow

    wk = RaceWeekend(year=year, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    race = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
    db_session.add(race)
    db_session.commit()
    db_session.refresh(race)
    return wk, race


def _add_stint(db_session, session, driver, lap_times, gaps):
    from telogify.models import Stint

    db_session.add(
        Stint(
            session_id=session.id, driver=driver, stint_number=1, lap_start=2,
            compound="SOFT", lap_times_json=lap_times, gaps_to_car_ahead_json=gaps,
        )
    )


def test_mine_clean_air_pace_fires_on_rank_divergence(db_session):
    wk, race = _seed_weekend(db_session, 2098)
    dc_map = {"VER": "Red Bull", "LEC": "Ferrari", "NOR": "McLaren"}
    # Red Bull: half its laps stuck behind traffic (dragging raw median to worst of the three,
    # 92.5) but the laps it ran in clear air were the fastest on track (clean-air median 85.0,
    # best of the three): the traffic picture and the true-pace picture disagree by 2 ranks.
    _add_stint(
        db_session, race, "VER",
        [100.0, 100.0, 100.0, 100.0, 100.0, 85.0, 85.0, 85.0, 85.0, 85.0],
        [0.1, 0.1, 0.1, 0.1, 0.1, None, None, None, None, None],
    )
    _add_stint(db_session, race, "LEC", [90.0] * 6, [None] * 6)
    _add_stint(db_session, race, "NOR", [91.0] * 6, [None] * 6)
    db_session.commit()

    signals = _mine_clean_air_pace(db_session, [race], dc_map)
    assert len(signals) == 1
    sig = signals[0]
    assert sig.subject == "Red Bull"
    assert sig.category == "clean_air_pace"
    assert sig.signal_type == "race_clean_air_pace"
    assert sig.source_refs[0]["median_rank"] == 3
    assert sig.source_refs[0]["clean_air_rank"] == 1


def test_mine_clean_air_pace_silent_when_ranks_agree(db_session):
    wk, race = _seed_weekend(db_session, 2097)
    dc_map = {"VER": "Red Bull", "LEC": "Ferrari"}
    _add_stint(db_session, race, "VER", [90.0] * 6, [None] * 6)
    _add_stint(db_session, race, "LEC", [92.0] * 6, [None] * 6)
    db_session.commit()

    assert _mine_clean_air_pace(db_session, [race], dc_map) == []


def test_mine_clean_air_pace_silent_below_min_lap_floor(db_session):
    wk, race = _seed_weekend(db_session, 2096)
    dc_map = {"VER": "Red Bull", "LEC": "Ferrari"}
    # Only 2 clean-air laps each, below MIN_CLEAN_AIR_LAPS: excluded as unreliable, even
    # though the ranks would otherwise diverge.
    _add_stint(db_session, race, "VER", [95.0, 95.0, 89.0, 89.0], [0.1, 0.1, None, None])
    _add_stint(db_session, race, "LEC", [90.0, 90.0, 90.0, 90.0], [None, None, None, None])
    db_session.commit()

    assert _mine_clean_air_pace(db_session, [race], dc_map) == []


def test_mine_clean_air_pace_silent_without_gap_data(db_session):
    from telogify.models import Stint

    wk, race = _seed_weekend(db_session, 2095)
    dc_map = {"VER": "Red Bull", "LEC": "Ferrari"}
    db_session.add(Stint(session_id=race.id, driver="VER", stint_number=1, compound="SOFT", lap_times_json=[90.0] * 6))
    db_session.add(Stint(session_id=race.id, driver="LEC", stint_number=1, compound="SOFT", lap_times_json=[91.0] * 6))
    db_session.commit()

    assert _mine_clean_air_pace(db_session, [race], dc_map) == []


def test_clean_air_pace_stacks_with_race_pace_on_correlate():
    # Same subject, distinct categories ("pace" vs "clean_air_pace"): correlate should fuse
    # them into one cross-channel candidate that outranks either alone.
    pace = Signal(signal_type="race_pace", category="pace", magnitude=0.5, confidence=1.0, subject="Ferrari")
    clean_air = Signal(
        signal_type="race_clean_air_pace", category="clean_air_pace", magnitude=0.3,
        confidence=1.0, subject="Ferrari",
    )
    signals = [pace, clean_air]
    normalize_and_score(signals)
    merged = correlate(signals)
    combined = next(s for s in merged if s.signal_type == "cross_session")
    assert combined.subject == "Ferrari"
    assert combined.robustness > pace.robustness
    assert combined.robustness > clean_air.robustness


def test_mine_corner_deltas_skips_none_delta_or_confidence(db_session):
    from telogify.analysis.candidates import _mine_corner_deltas
    from telogify.models import Attribution, RaceWeekend, Session as SessionRow

    wk = RaceWeekend(year=2094, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    q = SessionRow(weekend_id=wk.id, session_type="Q", status="loaded")
    db_session.add(q)
    db_session.commit()
    db_session.refresh(q)

    db_session.add_all(
        [
            Attribution(session_id=q.id, corner_number=1, constructor_a="Ferrari", constructor_b="McLaren", delta_s=None, confidence=1.0),
            Attribution(session_id=q.id, corner_number=2, constructor_a="Ferrari", constructor_b="McLaren", delta_s=0.1, confidence=None),
        ]
    )
    db_session.commit()

    assert _mine_corner_deltas(db_session, [q]) == []


def test_mine_straight_deltas_skips_single_constructor_and_slow_zones(db_session):
    from telogify.analysis.candidates import _mine_straight_deltas
    from telogify.models import RaceWeekend, Session as SessionRow, StraightSegment

    wk = RaceWeekend(year=2093, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    q = SessionRow(weekend_id=wk.id, session_type="Q", status="loaded")
    db_session.add(q)
    db_session.commit()
    db_session.refresh(q)

    db_session.add_all(
        [
            # zone 1: only one constructor present -> skipped (nothing to compare)
            StraightSegment(session_id=q.id, driver="LEC", drs_zone_id=1, max_speed_kmh=330.0),
            # zone 2: two constructors but both below REAL_STRAIGHT_KMH -> not a real straight
            StraightSegment(session_id=q.id, driver="VER", drs_zone_id=2, max_speed_kmh=250.0),
            StraightSegment(session_id=q.id, driver="HAM", drs_zone_id=2, max_speed_kmh=240.0),
        ]
    )
    db_session.commit()
    dc_map = {"LEC": "Ferrari", "VER": "Red Bull", "HAM": "Mercedes"}

    assert _mine_straight_deltas(db_session, [q], dc_map) == []


def test_mine_race_pace_covers_race_and_sprint_sessions(db_session):
    from telogify.analysis.candidates import _mine_race_pace
    from telogify.models import RaceWeekend, Session as SessionRow

    wk = RaceWeekend(year=2092, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    race = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
    sprint = SessionRow(weekend_id=wk.id, session_type="SPRINT", status="loaded")
    db_session.add(race)
    db_session.add(sprint)
    db_session.commit()
    db_session.refresh(race)
    db_session.refresh(sprint)

    dc_map = {"VER": "Red Bull", "LEC": "Ferrari"}
    _add_stint(db_session, race, "VER", [90.0] * 6, [None] * 6)
    _add_stint(db_session, race, "LEC", [92.0] * 6, [None] * 6)
    _add_stint(db_session, sprint, "VER", [45.0] * 6, [None] * 6)
    _add_stint(db_session, sprint, "LEC", [46.0] * 6, [None] * 6)
    db_session.commit()

    signals = _mine_race_pace(db_session, [race, sprint], dc_map)
    types = {s.signal_type for s in signals}
    assert types == {"race_pace", "sprint_pace"}
    assert all(s.subject == "Ferrari" for s in signals)  # the slower constructor


def test_mine_clean_air_pace_sprint_branch(db_session):
    from telogify.analysis.candidates import _mine_clean_air_pace
    from telogify.models import RaceWeekend, Session as SessionRow

    wk = RaceWeekend(year=2091, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    sprint = SessionRow(weekend_id=wk.id, session_type="SPRINT", status="loaded")
    db_session.add(sprint)
    db_session.commit()
    db_session.refresh(sprint)

    dc_map = {"VER": "Red Bull", "LEC": "Ferrari", "NOR": "McLaren"}
    _add_stint(
        db_session, sprint, "VER",
        [100.0, 100.0, 100.0, 100.0, 100.0, 85.0, 85.0, 85.0, 85.0, 85.0],
        [0.1, 0.1, 0.1, 0.1, 0.1, None, None, None, None, None],
    )
    _add_stint(db_session, sprint, "LEC", [90.0] * 6, [None] * 6)
    _add_stint(db_session, sprint, "NOR", [91.0] * 6, [None] * 6)
    db_session.commit()

    signals = _mine_clean_air_pace(db_session, [sprint], dc_map)
    assert len(signals) == 1
    assert signals[0].signal_type == "sprint_clean_air_pace"


def test_mine_sector_deltas_emits_signal(db_session):
    from telogify.analysis.candidates import _mine_sector_deltas
    from telogify.models import RaceWeekend, SectorBest, Session as SessionRow

    wk = RaceWeekend(year=2090, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    fp1 = SessionRow(weekend_id=wk.id, session_type="FP1", status="loaded")
    db_session.add(fp1)
    db_session.commit()
    db_session.refresh(fp1)

    db_session.add_all(
        [
            SectorBest(session_id=fp1.id, driver="LEC", sector=1, best_time_s=30.0),
            SectorBest(session_id=fp1.id, driver="VER", sector=1, best_time_s=30.5),
            # sector 2: only one constructor's driver is in dc_map -> excluded, then left with
            # a single constructor in that sector -> also skipped (len(by_constructor) < 2)
            SectorBest(session_id=fp1.id, driver="LEC", sector=2, best_time_s=20.0),
            SectorBest(session_id=fp1.id, driver="UNKNOWN", sector=2, best_time_s=19.5),
        ]
    )
    db_session.commit()
    dc_map = {"LEC": "Ferrari", "VER": "Red Bull"}

    signals = _mine_sector_deltas(db_session, [fp1], dc_map)
    assert len(signals) == 1
    assert signals[0].subject == "Red Bull"
    assert signals[0].category == "sector"
    assert signals[0].locus == "sector:1"


def test_mine_sector_deltas_no_practice_sessions(db_session):
    from telogify.analysis.candidates import _mine_sector_deltas
    from telogify.models import RaceWeekend, Session as SessionRow

    wk = RaceWeekend(year=2089, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    race = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
    db_session.add(race)
    db_session.commit()
    db_session.refresh(race)

    assert _mine_sector_deltas(db_session, [race], {}) == []


def test_mine_quali_character_top_speed_and_grip_deltas(db_session):
    from telogify.analysis.candidates import _mine_quali_character
    from telogify.models import QualiCharacter, RaceWeekend, Session as SessionRow

    wk = RaceWeekend(year=2088, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    q = SessionRow(weekend_id=wk.id, session_type="Q", status="loaded")
    db_session.add(q)
    db_session.commit()
    db_session.refresh(q)

    db_session.add_all(
        [
            QualiCharacter(session_id=q.id, driver="LEC", constructor="Ferrari", lap_time_s=90.0, top_speed_kmh=330.0, min_speed_kmh=80.0),
            QualiCharacter(session_id=q.id, driver="VER", constructor="Red Bull", lap_time_s=90.2, top_speed_kmh=320.0, min_speed_kmh=90.0),
            QualiCharacter(session_id=q.id, driver="NOR", constructor="McLaren", lap_time_s=90.4, top_speed_kmh=325.0, min_speed_kmh=None),
        ]
    )
    db_session.commit()

    signals = _mine_quali_character(db_session, [q])
    by_type = {s.signal_type for s in signals}
    assert "quali_top_speed_delta" in by_type
    assert "quali_grip_delta" in by_type
    grip_signals = [s for s in signals if s.signal_type == "quali_grip_delta"]
    # NOR has no min_speed_kmh, so it never enters the grip channel
    assert all(s.subject != "McLaren" for s in grip_signals)


def test_mine_quali_progression_for_session(db_session):
    from telogify.analysis.candidates import _mine_quali_progression
    from telogify.models import RaceWeekend, Session as SessionRow, SessionResult

    wk = RaceWeekend(year=2087, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    q = SessionRow(weekend_id=wk.id, session_type="Q", status="loaded")
    db_session.add(q)
    db_session.commit()
    db_session.refresh(q)

    db_session.add_all(
        [
            SessionResult(session_id=q.id, driver="LEC", constructor="Ferrari", q1_time_s=90.0, q2_time_s=89.0, q3_time_s=88.0),
            # HAM: same team, worse final time than LEC -> dedup keeps LEC as the rep
            SessionResult(session_id=q.id, driver="HAM", constructor="Ferrari", q1_time_s=90.5, q2_time_s=89.5, q3_time_s=None),
            SessionResult(session_id=q.id, driver="VER", constructor="Red Bull", q1_time_s=91.0, q2_time_s=90.0, q3_time_s=89.0),
            SessionResult(session_id=q.id, driver="NOR", constructor="McLaren", q1_time_s=92.0, q2_time_s=91.2, q3_time_s=None),
            SessionResult(session_id=q.id, driver="PER", constructor=None, q1_time_s=93.0),  # no constructor -> skipped
            SessionResult(session_id=q.id, driver="ALO", constructor="Aston Martin", q1_time_s=None),  # no Q1 -> skipped
            # eliminated in Q1 (no Q2 or Q3 time at all) -> skipped
            SessionResult(session_id=q.id, driver="GAS", constructor="Alpine", q1_time_s=94.0),
        ]
    )
    db_session.commit()

    signals = _mine_quali_progression(db_session, [q])
    assert {s.subject for s in signals} == {"Ferrari", "Red Bull", "McLaren"}
    assert all(s.signal_type == "quali_progression" for s in signals)


def test_mine_quali_progression_too_few_candidates(db_session):
    from telogify.analysis.candidates import _mine_quali_progression
    from telogify.models import RaceWeekend, Session as SessionRow, SessionResult

    wk = RaceWeekend(year=2086, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    q = SessionRow(weekend_id=wk.id, session_type="Q", status="loaded")
    db_session.add(q)
    db_session.commit()
    db_session.refresh(q)
    db_session.add_all(
        [
            SessionResult(session_id=q.id, driver="LEC", constructor="Ferrari", q1_time_s=90.0, q2_time_s=89.0),
            SessionResult(session_id=q.id, driver="VER", constructor="Red Bull", q1_time_s=91.0, q2_time_s=90.0),
        ]
    )
    db_session.commit()

    assert _mine_quali_progression(db_session, [q]) == []


def test_mine_quali_progression_too_few_distinct_constructors(db_session):
    from telogify.analysis.candidates import _mine_quali_progression
    from telogify.models import RaceWeekend, Session as SessionRow, SessionResult

    wk = RaceWeekend(year=2073, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    q = SessionRow(weekend_id=wk.id, session_type="Q", status="loaded")
    db_session.add(q)
    db_session.commit()
    db_session.refresh(q)
    # 3+ candidates, but only 2 distinct constructors after dedup -> below the reps floor
    db_session.add_all(
        [
            SessionResult(session_id=q.id, driver="LEC", constructor="Ferrari", q1_time_s=90.0, q2_time_s=89.0, q3_time_s=88.0),
            SessionResult(session_id=q.id, driver="HAM", constructor="Ferrari", q1_time_s=90.5, q2_time_s=89.5, q3_time_s=88.5),
            SessionResult(session_id=q.id, driver="VER", constructor="Red Bull", q1_time_s=91.0, q2_time_s=90.0, q3_time_s=89.0),
        ]
    )
    db_session.commit()

    assert _mine_quali_progression(db_session, [q]) == []


def test_mine_quali_pace_speed_correlation_for_session(db_session):
    from telogify.analysis.candidates import _mine_quali_pace_speed_correlation
    from telogify.models import QualiCharacter, RaceWeekend, Session as SessionRow

    wk = RaceWeekend(year=2085, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    q = SessionRow(weekend_id=wk.id, session_type="Q", status="loaded")
    db_session.add(q)
    db_session.commit()
    db_session.refresh(q)

    db_session.add_all(
        [
            QualiCharacter(session_id=q.id, driver="LEC", constructor="Ferrari", lap_time_s=87.0, top_speed_kmh=330.0),
            QualiCharacter(session_id=q.id, driver="VER", constructor="Red Bull", lap_time_s=88.0, top_speed_kmh=320.0),
            QualiCharacter(session_id=q.id, driver="HAM", constructor="Mercedes", lap_time_s=89.0, top_speed_kmh=310.0),
            # NOR is much slower on track than its top speed alone predicts -> real residual
            QualiCharacter(session_id=q.id, driver="NOR", constructor="McLaren", lap_time_s=91.0, top_speed_kmh=300.0),
        ]
    )
    db_session.commit()

    signals = _mine_quali_pace_speed_correlation(db_session, [q])
    assert len(signals) >= 1
    assert all(s.signal_type == "quali_pace_speed_residual" for s in signals)
    assert all(s.confidence == 0.75 for s in signals)


def test_mine_quali_pace_speed_correlation_no_spread(db_session):
    from telogify.analysis.candidates import _mine_quali_pace_speed_correlation
    from telogify.models import QualiCharacter, RaceWeekend, Session as SessionRow

    wk = RaceWeekend(year=2084, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    q = SessionRow(weekend_id=wk.id, session_type="Q", status="loaded")
    db_session.add(q)
    db_session.commit()
    db_session.refresh(q)

    # every car has the identical top speed -> no x-spread, linear_regression returns None
    db_session.add_all(
        [
            QualiCharacter(session_id=q.id, driver=d, constructor=c, lap_time_s=t, top_speed_kmh=320.0)
            for d, c, t in [("LEC", "Ferrari", 87.0), ("VER", "Red Bull", 88.0), ("HAM", "Mercedes", 89.0), ("NOR", "McLaren", 90.0)]
        ]
    )
    db_session.commit()

    assert _mine_quali_pace_speed_correlation(db_session, [q]) == []


def test_mine_degradation_race_and_sprint(db_session):
    from telogify.analysis.candidates import _mine_degradation
    from telogify.models import RaceWeekend, Session as SessionRow

    wk = RaceWeekend(year=2083, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    race = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
    sprint = SessionRow(weekend_id=wk.id, session_type="SPRINT", status="loaded")
    db_session.add(race)
    db_session.add(sprint)
    db_session.commit()
    db_session.refresh(race)
    db_session.refresh(sprint)

    dc_map = {"VER": "Red Bull"}
    ages = [1, 2, 3, 4, 5, 6]
    times = [90.0, 90.3, 90.6, 90.9, 91.2, 91.5]  # clear positive (degrading) slope
    from telogify.models import Stint

    db_session.add(Stint(session_id=race.id, driver="VER", stint_number=1, lap_start=2, compound="SOFT", lap_times_json=times, tyre_ages_json=ages))
    # constructor not in dc_map -> skipped entirely
    db_session.add(Stint(session_id=race.id, driver="UNKNOWN", stint_number=1, lap_start=2, compound="SOFT", lap_times_json=times, tyre_ages_json=ages))
    # a None tyre age mid-stint -> that lap is dropped
    db_session.add(Stint(session_id=race.id, driver="VER", stint_number=2, lap_start=20, compound="MEDIUM", lap_times_json=[91.0, 91.0], tyre_ages_json=[None, 1]))
    # flat (non-degrading) pace on HARD -> slope <= 0, no signal for this compound
    db_session.add(Stint(session_id=race.id, driver="VER", stint_number=3, lap_start=30, compound="HARD", lap_times_json=[90.0] * 6, tyre_ages_json=ages))
    db_session.add(Stint(session_id=sprint.id, driver="VER", stint_number=1, lap_start=2, compound="SOFT", lap_times_json=times, tyre_ages_json=ages))
    db_session.commit()

    signals = _mine_degradation(db_session, [race, sprint], dc_map)
    types = {s.signal_type for s in signals}
    assert types == {"tyre_degradation", "sprint_degradation"}
    assert all(s.subject == "Red Bull" for s in signals)


def test_mine_sprint_vs_race_pace_no_common_constructors(db_session):
    from telogify.analysis.candidates import _mine_sprint_vs_race_pace
    from telogify.models import RaceWeekend, Session as SessionRow

    wk = RaceWeekend(year=2082, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    race = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
    sprint = SessionRow(weekend_id=wk.id, session_type="SPRINT", status="loaded")
    db_session.add(race)
    db_session.add(sprint)
    db_session.commit()
    db_session.refresh(race)
    db_session.refresh(sprint)

    # entirely disjoint constructors between the two sessions -> no overlap to compare
    _add_stint(db_session, sprint, "VER", [45.0] * 6, [None] * 6)
    _add_stint(db_session, race, "LEC", [90.0] * 6, [None] * 6)
    db_session.commit()

    dc_map = {"VER": "Red Bull", "LEC": "Ferrari"}
    assert _mine_sprint_vs_race_pace(db_session, [sprint, race], dc_map) == []


def test_expected_ranks_missing_weekend_and_missing_snapshot(db_session, monkeypatch):
    from telogify.analysis import candidates as candidates_module
    from telogify.models import RaceWeekend

    assert candidates_module._expected_ranks(999_999_999, db_session) == {}

    year = 2081
    candidates_module._SEASON_SNAPSHOT_CACHE.pop(year, None)
    wk = RaceWeekend(year=year, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    monkeypatch.setattr(candidates_module, "build_season_snapshot", lambda y, db: None)

    try:
        assert candidates_module._expected_ranks(wk.id, db_session) == {}
    finally:
        candidates_module._SEASON_SNAPSHOT_CACHE.pop(year, None)


def test_actual_ranks_uses_best_finish_per_constructor(db_session):
    from telogify.analysis.candidates import _actual_ranks
    from telogify.models import RaceWeekend, Session as SessionRow, SessionResult

    wk = RaceWeekend(year=2080, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    race = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
    db_session.add(race)
    db_session.commit()
    db_session.refresh(race)

    db_session.add_all(
        [
            SessionResult(session_id=race.id, driver="LEC", constructor="Ferrari", position=1),
            SessionResult(session_id=race.id, driver="HAM", constructor="Ferrari", position=5),  # teammate, worse
            SessionResult(session_id=race.id, driver="VER", constructor="Red Bull", position=2),
            SessionResult(session_id=race.id, driver="OUT", constructor="Alpine", position=None),  # DNF, skipped
            SessionResult(session_id=race.id, driver="NON", constructor=None, position=3),  # no constructor, skipped
        ]
    )
    db_session.commit()

    ranks = _actual_ranks([race], db_session)
    assert ranks == {"Ferrari": 1, "Red Bull": 2}


def test_actual_ranks_without_a_race_session(db_session):
    from telogify.analysis.candidates import _actual_ranks
    from telogify.models import RaceWeekend, Session as SessionRow

    wk = RaceWeekend(year=2079, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    q = SessionRow(weekend_id=wk.id, session_type="Q", status="loaded")
    db_session.add(q)
    db_session.commit()
    db_session.refresh(q)

    assert _actual_ranks([q], db_session) == {}


def test_mine_deployment_skips_when_consistency_gate_leaves_one_constructor(db_session):
    from telogify.analysis.candidates import _mine_deployment
    from telogify.models import DeploymentTrace, RaceWeekend, Session as SessionRow

    wk = RaceWeekend(year=2078, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    q = SessionRow(weekend_id=wk.id, session_type="Q", status="loaded")
    db_session.add(q)
    db_session.commit()
    db_session.refresh(q)

    db_session.add_all(
        [
            # Ferrari: both cars clip -> passes the consistency gate
            DeploymentTrace(session_id=q.id, driver="LEC", constructor="Ferrari", total_clip_m=40.0, max_clip_m=40.0),
            DeploymentTrace(session_id=q.id, driver="HAM", constructor="Ferrari", total_clip_m=45.0, max_clip_m=45.0),
            # Williams: only one car clips (max_clip_m=0 on the other) -> fails the gate
            DeploymentTrace(session_id=q.id, driver="ALB", constructor="Williams", total_clip_m=200.0, max_clip_m=200.0),
            DeploymentTrace(session_id=q.id, driver="SAI", constructor="Williams", total_clip_m=0.0, max_clip_m=0.0),
        ]
    )
    db_session.commit()

    assert _mine_deployment(db_session, [q]) == []


def test_mine_ers_character_emits_signal_for_diverging_slope(db_session):
    from telogify.analysis.candidates import _mine_ers_character
    from telogify.models import AccelSample, RaceWeekend, Session as SessionRow

    wk = RaceWeekend(year=2077, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    race = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
    db_session.add(race)
    db_session.commit()
    db_session.refresh(race)

    speeds = [150.0, 165.0, 180.0, 195.0, 210.0, 225.0, 240.0, 250.0]

    def accel_for(slope, base):
        return [base + slope * s for s in speeds]

    db_session.add_all(
        [
            AccelSample(session_id=race.id, driver="VER", constructor="Red Bull", speed_kmh_json=speeds, longitudinal_accel_ms2_json=accel_for(0.03, 1.0)),
            AccelSample(session_id=race.id, driver="LEC", constructor="Ferrari", speed_kmh_json=speeds, longitudinal_accel_ms2_json=accel_for(0.01, 1.0)),
            AccelSample(session_id=race.id, driver="HAM", constructor="Mercedes", speed_kmh_json=speeds, longitudinal_accel_ms2_json=accel_for(0.005, 1.0)),
            # no constructor -> skipped
            AccelSample(session_id=race.id, driver="UNKNOWN", constructor=None, speed_kmh_json=speeds, longitudinal_accel_ms2_json=accel_for(0.02, 1.0)),
            # too few points inside the harvest band -> skipped, never reaches the slope fit
            AccelSample(session_id=race.id, driver="NOR", constructor="McLaren", speed_kmh_json=[150.0, 160.0], longitudinal_accel_ms2_json=[1.0, 1.02]),
        ]
    )
    db_session.commit()

    signals = _mine_ers_character(db_session, [race], {})
    assert len(signals) >= 1
    assert all(s.signal_type == "ers_deployment_character" for s in signals)
    assert all(s.category == "deployment" for s in signals)
    assert all(s.subject != "McLaren" for s in signals)


def test_mine_ers_character_too_few_valid_slopes(db_session):
    from telogify.analysis.candidates import _mine_ers_character
    from telogify.models import AccelSample, RaceWeekend, Session as SessionRow

    wk = RaceWeekend(year=2073, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    race = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
    db_session.add(race)
    db_session.commit()
    db_session.refresh(race)

    speeds = [150.0, 165.0, 180.0, 195.0, 210.0, 225.0, 240.0, 250.0]
    flat_speeds = [200.0] * 8  # no spread -> linear_regression returns None

    db_session.add_all(
        [
            AccelSample(session_id=race.id, driver="VER", constructor="Red Bull", speed_kmh_json=speeds, longitudinal_accel_ms2_json=[1.0 + 0.03 * s for s in speeds]),
            AccelSample(session_id=race.id, driver="LEC", constructor="Ferrari", speed_kmh_json=speeds, longitudinal_accel_ms2_json=[1.0 + 0.01 * s for s in speeds]),
            AccelSample(session_id=race.id, driver="HAM", constructor="Mercedes", speed_kmh_json=flat_speeds, longitudinal_accel_ms2_json=[1.0, 1.1, 1.2, 1.0, 1.1, 1.2, 1.0, 1.1]),
        ]
    )
    db_session.commit()

    # 3 constructors clear the by-constructor floor, but Mercedes' fit is None (no speed
    # spread), leaving only 2 valid slopes -> below the slopes floor.
    assert _mine_ers_character(db_session, [race], {}) == []


def test_mine_ers_character_too_few_constructors(db_session):
    from telogify.analysis.candidates import _mine_ers_character
    from telogify.models import AccelSample, RaceWeekend, Session as SessionRow

    wk = RaceWeekend(year=2076, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    race = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
    db_session.add(race)
    db_session.commit()
    db_session.refresh(race)

    speeds = [150.0, 165.0, 180.0, 195.0, 210.0, 225.0, 240.0, 250.0]
    db_session.add(
        AccelSample(session_id=race.id, driver="VER", constructor="Red Bull", speed_kmh_json=speeds, longitudinal_accel_ms2_json=[1.0] * len(speeds))
    )
    db_session.commit()

    assert _mine_ers_character(db_session, [race], {}) == []


def test_compute_candidates_full_weekend_persists_ranked_signals(db_session):
    from telogify.models import Attribution, CandidateInsight, RaceWeekend, Session as SessionRow

    wk = RaceWeekend(year=2075, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    q = SessionRow(weekend_id=wk.id, session_type="Q", status="loaded")
    race = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
    db_session.add(q)
    db_session.add(race)
    db_session.commit()
    db_session.refresh(q)
    db_session.refresh(race)

    db_session.add(
        Attribution(session_id=q.id, corner_number=1, constructor_a="Ferrari", constructor_b="McLaren", delta_s=2.0, confidence=0.9)
    )
    db_session.commit()

    ranked = compute_candidates(wk.id, db_session)
    assert len(ranked) >= 1
    stored = db_session.exec(
        select(CandidateInsight).where(CandidateInsight.weekend_id == wk.id)
    ).all()
    assert len(stored) == len(ranked)


def test_compute_candidates_runs_with_only_a_quali_session(db_session):
    # Mid-weekend, quali-only ingest (no race session at all): compute_candidates is now called
    # in this exact shape by the pipeline once qualifying is in but the race hasn't happened.
    # Every miner resolves its sessions via pick_session, which returns None for the missing
    # "R"/"SPRINT" types, so this must not raise even with zero race data anywhere.
    from telogify.models import RaceWeekend, Session as SessionRow

    wk = RaceWeekend(year=2099, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    db_session.add(SessionRow(weekend_id=wk.id, session_type="Q", status="loaded"))
    db_session.commit()

    signals = compute_candidates(wk.id, db_session)
    assert signals == []
