from telogify.ingest.results import (
    compound_letter,
    compute_gap,
    format_gap_label,
    format_total_time,
    is_lapped,
    laps_down,
    race_points,
    strategy_string,
)


def test_race_points_by_position():
    assert race_points(1) == 25
    assert race_points(10) == 1
    assert race_points(11) == 0
    assert race_points(None) == 0


def test_compound_letter():
    assert compound_letter("SOFT") == "S"
    assert compound_letter("intermediate") == "I"
    assert compound_letter(None) == "?"
    assert compound_letter("Experimental") == "E"  # unknown -> first letter


def test_strategy_string():
    assert strategy_string(["MEDIUM", "HARD", "MEDIUM"]) == "M-H-M"
    assert strategy_string(["SOFT", "MEDIUM"]) == "S-M"
    assert strategy_string([None]) == "?"
    assert strategy_string([]) == ""


def test_format_total_time():
    assert format_total_time(5432.106) == "1:30:32.106"
    assert format_total_time(92.5) == "1:32.500"  # hours dropped when zero
    assert format_total_time(None) is None


def test_leader_gap_is_zero_in_race():
    assert compute_gap(1, 5400.0, is_race=True) == 0.0


def test_follower_gap_is_time_in_race():
    assert compute_gap(2, 12.3, is_race=True) == 12.3


def test_non_race_has_no_gap():
    assert compute_gap(1, 80.0, is_race=False) is None


def test_missing_time_has_no_gap():
    assert compute_gap(5, None, is_race=True) is None


def test_lapped_driver_has_no_time_gap():
    assert (
        compute_gap(
            9,
            15.334,
            is_race=True,
            status="Lapped",
            laps=70.0,
            leader_laps=71.0,
        )
        is None
    )


def test_is_lapped_by_status_or_lap_count():
    assert is_lapped("Lapped", 70.0, 71.0)
    assert is_lapped("Finished", 69.0, 71.0)
    assert not is_lapped("Finished", 71.0, 71.0)


def test_laps_down():
    assert laps_down(70.0, 71.0) == 1
    assert laps_down(68.0, 71.0) == 3
    assert laps_down(71.0, 71.0) is None


def test_format_gap_label_multi_lap():
    leader = 71.0
    assert format_gap_label(1, 0.0, 71.0, leader, "Finished") == "leader"
    assert format_gap_label(2, 1.6, 71.0, leader, "Finished") == "+1.6s"
    assert format_gap_label(9, None, 70.0, leader, "Lapped") == "+1 Lap"
    assert format_gap_label(16, None, 69.0, leader, "Lapped") == "+2 Laps"
    assert format_gap_label(18, None, 68.0, leader, "Lapped") == "+3 Laps"
    assert format_gap_label(19, None, 45.0, leader, "Retired") == "DNF"
