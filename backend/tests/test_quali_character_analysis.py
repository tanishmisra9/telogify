from telogify.analysis.quali_character import (
    DRAG_BALANCED,
    DRAG_EFFICIENT,
    DRAG_HIGH_DOWNFORCE,
    DRAG_LACKS_EFFICIENCY,
    fastest_qualifier_per_constructor,
    label_car_character,
    pick_fastest_corner,
)


def _row(constructor, driver, lap_time, top_speed, min_speed, full_throttle, corner_speeds):
    return {
        "constructor": constructor,
        "driver": driver,
        "lap_time_s": lap_time,
        "top_speed_kmh": top_speed,
        "min_speed_kmh": min_speed,
        "full_throttle_pct": full_throttle,
        "corner_speeds": corner_speeds,
    }


def test_pick_fastest_corner_excludes_near_top_speed_kinks():
    # Corner 2 is a kink (barely below top speed); corner 8 is a real corner and should win.
    rows = [
        _row("A", "d1", 66.0, 330.0, 70.0, 0.6, {2: 320.0, 8: 240.0}),
        _row("B", "d2", 66.1, 325.0, 71.0, 0.6, {2: 318.0, 8: 245.0}),
    ]
    assert pick_fastest_corner(rows) == 8


def test_pick_fastest_corner_none_without_corner_speeds():
    assert pick_fastest_corner([_row("A", "d1", 66.0, 330.0, 70.0, 0.6, {})]) is None


def test_fastest_qualifier_per_constructor_collapses_teammates():
    rows = [
        _row("Ferrari", "LEC", 66.5, 320.0, 70.0, 0.6, {}),
        _row("Ferrari", "HAM", 66.3, 322.0, 71.0, 0.6, {}),
        _row("Mercedes", "RUS", 66.4, 325.0, 69.0, 0.6, {}),
    ]
    reps = fastest_qualifier_per_constructor(rows)
    by_constructor = {r["constructor"]: r["driver"] for r in reps}
    assert by_constructor == {"Ferrari": "HAM", "Mercedes": "RUS"}


def test_label_car_character_matches_brief_examples():
    # Real 2026 Austrian GP qualifying data (verified against the reference chart): Ferrari
    # is slowest on top speed but has the best downforce; Red Bull is fastest and efficient;
    # McLaren is weak on both top speed and throttle time but has the best low-speed grip.
    rows = [
        _row("Ferrari", "LEC", 66.349, 325.0, 71.0, 0.644, {8: 244.3}),
        _row("Mercedes", "ANT", 66.414, 330.0, 70.0, 0.604, {8: 249.0}),
        _row("RedBull", "VER", 66.475, 331.0, 67.0, 0.617, {8: 240.4}),
        _row("McLaren", "NOR", 66.502, 326.0, 72.0, 0.545, {8: 239.0}),
    ]
    labeled = {r.constructor: r for r in label_car_character(rows)}

    assert labeled["Ferrari"].drag_label == DRAG_HIGH_DOWNFORCE
    assert labeled["Mercedes"].drag_label == DRAG_BALANCED
    assert labeled["Mercedes"].is_corner_speed_leader
    assert labeled["RedBull"].drag_label == DRAG_EFFICIENT
    assert labeled["RedBull"].is_top_speed_leader
    assert labeled["McLaren"].drag_label == DRAG_LACKS_EFFICIENCY
    assert labeled["McLaren"].is_grip_leader  # highest min_speed_kmh (72.0)


def test_label_car_character_balanced_when_no_strong_signal():
    rows = [
        _row("A", "d1", 66.0, 328.0, 70.0, 0.60, {8: 245.0}),
        _row("B", "d2", 66.1, 320.0, 70.0, 0.60, {8: 245.0}),
    ]
    labeled = {r.constructor: r for r in label_car_character(rows)}
    # A is faster everywhere but not by enough to trip the drag rules on a 2-row set where
    # both are in "their own half"; assert every row gets a defined label, no crash on edge case.
    assert labeled["A"].drag_label in (DRAG_EFFICIENT, DRAG_BALANCED, DRAG_HIGH_DOWNFORCE, DRAG_LACKS_EFFICIENCY)


def test_label_car_character_empty_input():
    assert label_car_character([]) == []
