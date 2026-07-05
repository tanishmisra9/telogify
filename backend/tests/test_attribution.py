from telogify.analysis.attribution import (
    DriverCorner,
    aggregate_driver_corner,
    attribute_corner,
    classify_speed,
)


# --- Rule 1: confidence-weighted mean (not sum) ---
def test_aggregate_is_lap_weighted_mean():
    metric, total = aggregate_driver_corner([(200.0, 5), (210.0, 15)])
    assert total == 20
    assert abs(metric - 207.5) < 1e-9  # (200*5 + 210*15) / 20, not a sum


# --- Rule 2: low-sample capping ---
def test_aggregate_excludes_thin_compound():
    metric, total = aggregate_driver_corner([(150.0, 3), (200.0, 10)])
    assert total == 10  # the 3-lap compound dropped
    assert metric == 200.0


def test_aggregate_all_thin_returns_none():
    assert aggregate_driver_corner([(150.0, 2), (160.0, 4)]) is None


# --- car vs driver split ---
def test_car_dominated_split():
    a = [DriverCorner("McLaren", "NOR", 210.0, 8), DriverCorner("McLaren", "PIA", 208.0, 8)]
    b = [DriverCorner("Ferrari", "LEC", 200.0, 8), DriverCorner("Ferrari", "HAM", 198.0, 8)]
    attr = attribute_corner(7, a, b)

    assert abs(attr.delta_s - 10.0) < 1e-9  # car_a 209 - car_b 199
    assert attr.car_pct > attr.driver_pct  # 10 km/h gap dwarfs 2 km/h teammate spread
    assert attr.confidence == 1.0  # both teams two strong drivers


# --- Rule 3: teammate reliability caps confidence ---
def test_single_driver_team_caps_confidence():
    a = [DriverCorner("Williams", "ALB", 210.0, 8)]  # only one driver
    b = [DriverCorner("Ferrari", "LEC", 200.0, 8), DriverCorner("Ferrari", "HAM", 198.0, 8)]
    attr = attribute_corner(7, a, b)
    assert attr.confidence == 0.5  # 1.0 base * teammate cap


def test_weak_teammate_baseline_caps_confidence():
    # one driver under the 60% baseline (4/8 = 0.5) -> team unreliable, and min_laps drives base conf
    a = [DriverCorner("RB", "VER", 210.0, 8), DriverCorner("RB", "LAW", 208.0, 4)]
    b = [DriverCorner("Ferrari", "LEC", 200.0, 8), DriverCorner("Ferrari", "HAM", 198.0, 8)]
    attr = attribute_corner(7, a, b)
    assert attr.confidence == 0.25  # base 4/8=0.5 * cap 0.5


def test_classify_speed_bands():
    from telogify.analysis.attribution import LOW_MAX_KMH, MID_MAX_KMH

    assert classify_speed(LOW_MAX_KMH - 0.1) == "low"
    assert classify_speed(LOW_MAX_KMH) == "mid"
    assert classify_speed(MID_MAX_KMH - 0.1) == "mid"
    assert classify_speed(MID_MAX_KMH) == "high"
    assert classify_speed(250.0) == "high"
