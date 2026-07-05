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


def test_lift_ending_run_is_not_a_clip():
    # big drop but the run ends in a LIFT (lift-coast / corner approach), not braking -> not a clip
    rise = [(200 + 12 * k, 100, False) for k in range(10)]
    fall = [(300, 100, False), (285, 100, False), (270, 100, False), (255, 100, False)]  # -45 km/h
    from telogify.analysis.deployment import detect_clipping
    runs = detect_clipping(*_trace(rise + fall + [(250, 30, False)]), min_straight_m=100)  # ends by lift
    assert runs and runs[0].end_reason == "lift" and not runs[0].is_clip


def test_drag_plateau_is_not_a_clip():
    # long run, ends in braking, but speed barely falls (drag-limited, not deployment) -> not a clip
    rise = [(240 + 10 * k, 100, False) for k in range(9)]           # up to ~320
    plateau = [(322, 100, False)] * 8 + [(320, 100, False)]          # holds, tiny drop
    from telogify.analysis.deployment import detect_clipping
    runs = detect_clipping(*_trace(rise + plateau + [(300, 100, True)]), min_straight_m=100)
    assert runs and not runs[0].is_clip  # drop < MIN_DROP


def test_low_speed_run_is_not_a_clip():
    # a slow corner-exit squirt that falls, ends in braking, but is nowhere near top speed
    from telogify.analysis.deployment import detect_clipping
    fast = [(240 + 10 * k, 100, False) for k in range(10)] + [(330, 100, True)]  # sets lap top ~330
    slow = [(150, 100, False), (165, 100, False), (178, 100, False), (188, 100, False),
            (185, 100, False), (176, 100, False), (168, 100, False), (155, 100, True)]  # peak 188 << 0.85*330, ~140m before brake
    d, sp, th, br = _trace(fast + slow, start=0)
    runs = detect_clipping(d, sp, th, br, min_straight_m=100)
    low = [r for r in runs if r.peak_kmh < 250]
    assert low and not low[0].is_clip


def test_clip_boundary_exactly_at_min_drop_and_min_clip_m():
    # ends in braking, high speed, drop == MIN_DROP (12), clip_m == MIN_CLIP_M (40)
    rise = [(240 + 10 * k, 100, False) for k in range(9)]  # 240..320, peak at d=160
    clip = [(308, 100, False), (308, 100, False)]  # 40m past peak, drop 12 km/h
    samples = rise + clip + [(308, 100, True)]
    runs = detect_clipping(*_trace(samples), min_straight_m=100)
    assert len(runs) == 1
    r = runs[0]
    assert r.end_reason == "brake"
    assert r.drop_kmh >= 12 and r.clip_m >= 40
    assert r.is_clip


def test_clip_rejected_when_drop_below_min():
    # Same geometry as boundary test but only 11 km/h drop -> not a clip
    rise = [(240 + 10 * k, 100, False) for k in range(9)]  # peak 320 at d=160
    clip = [(315, 100, False), (309, 100, False)]  # drop 11 km/h from peak 320
    samples = rise + clip + [(309, 100, True)]
    runs = detect_clipping(*_trace(samples), min_straight_m=100)
    assert len(runs) == 1
    assert runs[0].drop_kmh < 12
    assert not runs[0].is_clip


def test_clip_rejected_when_clip_distance_below_min():
    # 15 km/h drop but only 20m past peak -> not a clip
    rise = [(240 + 10 * k, 100, False) for k in range(9)]  # peak 320 at d=160
    clip = [(305, 100, False)]  # one sample, 20m past peak, drop 15
    samples = rise + clip + [(305, 100, True)]
    runs = detect_clipping(*_trace(samples), min_straight_m=100)
    assert len(runs) == 1
    assert runs[0].clip_m < 40
    assert not runs[0].is_clip
