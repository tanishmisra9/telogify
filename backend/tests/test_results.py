from telogify.ingest.results import compute_gap


def test_leader_gap_is_zero_in_race():
    assert compute_gap(1, 5400.0, is_race=True) == 0.0


def test_follower_gap_is_time_in_race():
    assert compute_gap(2, 12.3, is_race=True) == 12.3


def test_non_race_has_no_gap():
    assert compute_gap(1, 80.0, is_race=False) is None


def test_missing_time_has_no_gap():
    assert compute_gap(5, None, is_race=True) is None
