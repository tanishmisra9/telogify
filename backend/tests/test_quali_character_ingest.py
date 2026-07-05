from telogify.ingest.quali_character import (
    corner_min_speeds,
    full_throttle_fraction,
    is_representative_lap,
    lap_character,
)

GOOD = dict(is_accurate=True, deleted=False, in_out_lap=False, rainfall=False)


def test_representative_lap_accepts_clean_green_lap():
    assert is_representative_lap(**GOOD)


def test_representative_lap_has_no_track_status_param():
    """Regression guard for the audited bug: a real pole lap (IsAccurate, not deleted)
    was being dropped because FastF1 tagged a trailing caution onto its TrackStatus
    (e.g. "12" for a yellow thrown right as the lap ends), even though the flying lap
    itself was clean and officially counted. Unlike segment.is_clean_lap, this selector
    must not take a track_status argument, so that class of lap can never be excluded
    here again."""
    import inspect

    assert "track_status" not in inspect.signature(is_representative_lap).parameters


def test_representative_lap_excludes_inaccurate_deleted_in_out_wet():
    assert not is_representative_lap(**{**GOOD, "is_accurate": False})
    assert not is_representative_lap(**{**GOOD, "deleted": True})
    assert not is_representative_lap(**{**GOOD, "in_out_lap": True})
    assert not is_representative_lap(**{**GOOD, "rainfall": True})


def test_full_throttle_fraction_counts_at_or_above_threshold():
    assert full_throttle_fraction([100, 100, 50, 99, 98], threshold=99.0) == 0.6


def test_full_throttle_fraction_empty_is_zero():
    assert full_throttle_fraction([]) == 0.0


def test_full_throttle_fraction_drops_error_samples_above_100():
    # FastF1 emits 104 for unavailable throttle; exclude from denominator, not just numerator.
    assert full_throttle_fraction([100, 104, 100], threshold=99.0) == 1.0
    assert full_throttle_fraction([104, 104], threshold=99.0) == 0.0


def test_corner_min_speeds_one_entry_per_corner():
    distance = [0, 10, 20, 30, 40, 50]
    speed = [300, 100, 110, 300, 90, 300]
    windows = [(1, 5, 25), (2, 35, 45)]
    out = corner_min_speeds(distance, speed, windows)
    assert out == {1: 100, 2: 90}


def test_corner_min_speeds_skips_windows_with_no_samples():
    out = corner_min_speeds([0, 100], [250, 260], [(1, 1000, 1100)])
    assert out == {}


def test_lap_character_combines_all_four_metrics():
    distance = [0, 10, 20, 30]
    speed = [300, 100, 110, 300]
    throttle = [100, 0, 0, 100]
    windows = [(1, 5, 25)]
    char = lap_character(distance, speed, throttle, windows)
    assert char.top_speed_kmh == 300
    assert char.min_speed_kmh == 100
    assert char.corner_speeds_kmh == {1: 100}
    assert char.full_throttle_pct == 0.5


def test_lap_character_none_when_no_telemetry():
    assert lap_character([], [], [], []) is None
