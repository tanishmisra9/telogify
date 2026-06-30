from telogify.ingest.straights import find_straights


def test_find_straights_splits_on_corner_and_computes_max_and_trap():
    distance = [i * 10.0 for i in range(20)]
    speed = [
        200, 250, 280, 300, 310, 305,  # straight 1 (idx 0-5)
        300, 295, 290, 285, 280,       # corner (idx 6-10, distances 60-100)
        220, 260, 290, 310, 320, 330, 335, 332, 328,  # straight 2 (idx 11-19)
    ]
    throttle = [100.0] * 20
    windows = [(1, 60.0, 100.0)]

    segs = find_straights(distance, speed, throttle, windows, min_samples=5)

    assert len(segs) == 2
    assert segs[0].drs_zone_id == 1
    assert segs[0].max_speed_kmh == 310 and segs[0].trap_speed_kmh == 305
    assert segs[1].drs_zone_id == 2
    assert segs[1].max_speed_kmh == 335 and segs[1].trap_speed_kmh == 328


def test_find_straights_drops_short_runs_and_low_throttle():
    distance = [0.0, 10, 20, 30, 40, 50, 60, 70]
    speed = [300, 305, 310, 100, 100, 280, 290, 295]
    # only idx 0-2 are high throttle (a 3-sample blip); rest below threshold
    throttle = [100.0, 100, 100, 50, 50, 50, 50, 50]

    assert find_straights(distance, speed, throttle, [], min_samples=5) == []
    assert len(find_straights(distance, speed, throttle, [], min_samples=3)) == 1
