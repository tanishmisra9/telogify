import pytest

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
