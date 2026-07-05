from telogify.analysis.deployment import detect_clipping, summarize_deployment


def _trace(samples, step=20, start=0):
    """samples: list of (speed, throttle, brake); distance advances `step` m per sample."""
    d = [start + step * k for k in range(len(samples))]
    return d, [s[0] for s in samples], [s[1] for s in samples], [s[2] for s in samples]


def test_detects_a_clip_where_speed_falls_at_full_throttle():
    # rise to a peak (~310), then speed falls over several samples at full throttle, then brake
    rise = [(240 + 10 * k, 100, False) for k in range(8)]           # 240..310
    clip = [(306, 100, False), (302, 100, False), (298, 100, False)]  # ~60m falling at full throttle
    samples = rise + clip + [(280, 100, True)]
    runs = detect_clipping(*_trace(samples), min_straight_m=100)
    assert len(runs) == 1
    r = runs[0]
    assert r.is_clip and r.end_reason == "brake"
    assert r.clip_m >= 40 and r.drop_kmh >= 2


def test_no_clip_when_still_accelerating_to_the_brake_point():
    samples = [(150 + 12 * k, 100, False) for k in range(15)] + [(330, 100, True)]  # monotonic then brake
    runs = detect_clipping(*_trace(samples), min_straight_m=100)
    assert len(runs) == 1 and not runs[0].is_clip


def test_ignores_short_squirts():
    samples = [(120, 100, False), (140, 100, False), (150, 100, True)]  # ~40m, below any real straight
    assert detect_clipping(*_trace(samples)) == []


def test_lift_ends_a_run_and_is_reported():
    rise = [(200 + 12 * k, 100, False) for k in range(10)]          # 200..308
    coast = [(305, 100, False), (300, 100, False), (296, 100, False)]  # falling at full throttle
    samples = rise + coast + [(290, 40, False)]  # throttle lifts (not braking)
    runs = detect_clipping(*_trace(samples), min_straight_m=100)
    assert len(runs) == 1 and runs[0].end_reason == "lift"


def test_summary_aggregates_clips():
    rise = [(240 + 8 * k, 100, False) for k in range(11)]            # 240..320
    clip = [(316, 100, False), (312, 100, False), (308, 100, False)]  # ~60m falling
    runs = detect_clipping(*_trace(rise + clip + [(300, 100, True)]), min_straight_m=100)
    s = summarize_deployment(runs)
    assert s["n_clips"] == 1 and s["total_clip_m"] >= 40 and s["top_speed_kmh"] >= 320
