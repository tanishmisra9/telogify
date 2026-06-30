from telogify.ingest.straights import speed_in_zone, zone_windows


def test_zone_windows_are_corner_gaps_plus_wrap():
    zones = zone_windows([200.0, 500.0, 900.0], lap_length=1500.0, margin=50.0)
    assert zones == [
        (1, [(250.0, 450.0)]),
        (2, [(550.0, 850.0)]),
        (0, [(950.0, 1500.0), (0.0, 150.0)]),  # start/finish straight wraps the line
    ]


def test_zone_ids_are_stable_across_drivers():
    # Same circuit geometry -> identical zone ids regardless of who is driving.
    a = zone_windows([200.0, 500.0, 900.0], 1500.0)
    b = zone_windows([200.0, 500.0, 900.0], 1500.0)
    assert [z[0] for z in a] == [z[0] for z in b]


def test_speed_in_zone_max_and_trap():
    distance = [0.0, 100, 200, 300, 400, 500]
    speed = [100, 200, 310, 305, 150, 140]
    # window covers idx 2 (d=200) and idx 3 (d=300)
    assert speed_in_zone(distance, speed, [(150.0, 350.0)]) == (310.0, 305.0)


def test_speed_in_zone_empty_returns_none():
    assert speed_in_zone([0.0, 100.0], [250.0, 260.0], [(1000.0, 1100.0)]) is None
