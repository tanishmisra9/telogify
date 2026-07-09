import pytest

from telogify.ingest.stints import compute_gaps_to_car_ahead, fuel_effect_for_race, summarize_stint


def _lap(n, t, *, out=False, inn=False, acc=True, deleted=False, compound="MEDIUM", track_status="1", tyre_age=None):
    return dict(
        lap_number=n,
        lap_time_s=t,
        compound=compound,
        is_outlap=out,
        is_inlap=inn,
        is_accurate=acc,
        deleted=deleted,
        track_status=track_status,
        tyre_age=tyre_age,
    )


def test_summarize_stint_excludes_in_out_and_inaccurate():
    laps = [
        _lap(5, 95.0, out=True),   # outlap, excluded from pace
        _lap(6, 90.0),
        _lap(7, 90.5),
        _lap(8, 200.0, acc=False),  # inaccurate (e.g. SC), excluded
        _lap(9, 91.0),
        _lap(10, 96.0, inn=True),  # inlap, excluded
    ]
    s = summarize_stint(2, laps)

    assert s.stint_number == 2
    assert s.compound == "MEDIUM"
    assert s.lap_start == 5 and s.lap_end == 10  # full range retained
    assert s.lap_times == [90.0, 90.5, 91.0]
    assert abs(s.avg_pace - 90.5) < 1e-9


def test_summarize_stint_excludes_deleted_laps():
    # A steward-deleted lap (track limits) is IsAccurate + green but illegally fast: dropped.
    laps = [
        _lap(1, 90.0),
        _lap(2, 88.0, deleted=True),  # track-limits deletion, excluded despite fast time
        _lap(3, 90.5),
    ]
    s = summarize_stint(1, laps)
    assert s.lap_times == [90.0, 90.5]
    assert abs(s.avg_pace - 90.25) < 1e-9


def test_summarize_stint_all_excluded_gives_none_pace():
    s = summarize_stint(1, [_lap(1, 100.0, out=True), _lap(2, 101.0, inn=True)])
    assert s.lap_times == []
    assert s.avg_pace is None


def test_summarize_stint_excludes_sc_vsc_laps():
    """Laps run under safety car (TrackStatus != "1") must be excluded from pace."""
    laps = [
        _lap(1, 90.0),                       # green, kept
        _lap(2, 110.0, track_status="4"),    # safety car, excluded
        _lap(3, 111.0, track_status="6"),    # VSC, excluded
        _lap(4, 90.5),                       # green, kept
        _lap(5, 90.2, track_status="7"),     # VSC ending, excluded
        _lap(6, 91.0),                       # green, kept
    ]
    s = summarize_stint(1, laps)
    assert s.lap_times == [90.0, 90.5, 91.0]
    assert abs(s.avg_pace - 90.5) < 1e-9


def test_summarize_stint_fuel_correction():
    """Fuel correction reduces lap times; later laps get a smaller correction."""
    # Race has 10 laps total; fuel_effect = 0.1 s/lap.
    # Lap 8: raw=91.0 -> corrected = 91.0 - 0.1*(10-8) = 91.0 - 0.2 = 90.8
    # Lap 9: raw=91.0 -> corrected = 91.0 - 0.1*(10-9) = 91.0 - 0.1 = 90.9
    laps = [_lap(8, 91.0), _lap(9, 91.0)]
    s = summarize_stint(1, laps, total_laps=10, fuel_effect=0.1)
    assert abs(s.lap_times[0] - 90.8) < 1e-9
    assert abs(s.lap_times[1] - 90.9) < 1e-9
    assert abs(s.avg_pace - 90.85) < 1e-9


def test_summarize_stint_no_fuel_correction_when_params_absent():
    """Without total_laps/fuel_effect the raw times are stored unchanged."""
    laps = [_lap(1, 90.0), _lap(2, 91.0)]
    s = summarize_stint(1, laps)
    assert s.lap_times == [90.0, 91.0]


def test_summarize_stint_sc_lap_also_inaccurate_still_excluded():
    """SC lap with is_accurate=False: excluded once by SC check, not double-counted."""
    laps = [_lap(1, 90.0), _lap(2, 115.0, acc=False, track_status="4")]
    s = summarize_stint(1, laps)
    assert s.lap_times == [90.0]


def test_summarize_stint_tyre_ages_aligned_with_lap_times():
    """tyre_ages must stay index-for-index with lap_times, surviving the same exclusions."""
    laps = [
        _lap(1, 95.0, out=True, tyre_age=0),  # outlap, excluded
        _lap(2, 90.0, tyre_age=1),
        _lap(3, 200.0, acc=False, tyre_age=2),  # inaccurate, excluded
        _lap(4, 90.5, tyre_age=3),
    ]
    s = summarize_stint(1, laps)
    assert s.lap_times == [90.0, 90.5]
    assert s.tyre_ages == [1, 3]


def test_summarize_stint_tyre_age_missing_is_none():
    laps = [_lap(1, 90.0)]  # tyre_age defaults to None
    s = summarize_stint(1, laps)
    assert s.tyre_ages == [None]


def test_fuel_effect_for_race_matches_kg_and_cost_per_kg():
    # 70kg race allowance (2026 regs) at 0.025 s/kg over a 70-lap race -> 1kg/lap -> 0.025 s/lap.
    assert fuel_effect_for_race(70) == pytest.approx(0.025)
    # A shorter race burns fuel faster per lap, so the same total kg costs more time per lap.
    assert fuel_effect_for_race(35) == pytest.approx(0.05)


def _gap_lap(driver, lap_number, position, session_time_s):
    return dict(driver=driver, lap_number=lap_number, position=position, session_time_s=session_time_s)


def test_compute_gaps_to_car_ahead_leader_is_none():
    laps = [
        _gap_lap("VER", 10, 1, 1000.0),
        _gap_lap("HAM", 10, 2, 1002.5),
        _gap_lap("LEC", 10, 3, 1005.0),
    ]
    gaps = compute_gaps_to_car_ahead(laps)
    assert gaps[("VER", 10)] is None
    assert gaps[("HAM", 10)] == pytest.approx(2.5)
    assert gaps[("LEC", 10)] == pytest.approx(2.5)


def test_compute_gaps_to_car_ahead_skips_missing_position_or_time():
    laps = [
        _gap_lap("VER", 5, 1, 500.0),
        _gap_lap("HAM", 5, None, 503.0),  # missing position, e.g. retired/no classification
        _gap_lap("LEC", 5, 2, None),  # missing time
    ]
    gaps = compute_gaps_to_car_ahead(laps)
    assert ("HAM", 5) not in gaps
    assert ("LEC", 5) not in gaps
    assert gaps[("VER", 5)] is None
