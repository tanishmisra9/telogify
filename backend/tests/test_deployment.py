import numpy as np

from telogify.analysis.deployment import (
    DEPLETION_RESIDUAL_MS2,
    detect_clipping,
    summarize_deployment,
)


def _trace(samples, step=20, start=0):
    """samples: list of (speed, throttle, brake); distance advances `step` m per sample."""
    d = [start + step * k for k in range(len(samples))]
    return d, [s[0] for s in samples], [s[1] for s in samples], [s[2] for s in samples]


def _trace_with_time(samples, step=20, start=0):
    d, sp, th, br = _trace(samples, step=step, start=start)
    v = np.maximum(np.array(sp) / 3.6, 1.0)
    dt = step / v[:-1]
    t = [0.0]
    for x in dt:
        t.append(t[-1] + x)
    return d, sp, th, br, t


def test_detects_a_clip_where_speed_falls_at_full_throttle():
    rise = [(240 + 10 * k, 100, False) for k in range(8)]
    clip = [(305, 100, False), (298, 100, False), (290, 100, False), (282, 100, False)]
    samples = rise + clip + [(275, 100, True)]
    runs = detect_clipping(*_trace(samples), min_straight_m=100)
    assert len(runs) == 1
    r = runs[0]
    assert r.is_clip and r.end_reason == "brake"
    assert r.clip_m >= 40


def test_no_clip_when_still_accelerating_to_the_brake_point():
    samples = [(150 + 12 * k, 100, False) for k in range(15)] + [(330, 100, True)]
    runs = detect_clipping(*_trace(samples), min_straight_m=100)
    assert len(runs) == 1 and not runs[0].is_clip


def test_ignores_short_squirts():
    samples = [(120, 100, False), (140, 100, False), (150, 100, True)]
    assert detect_clipping(*_trace(samples)) == []


def test_lift_ends_a_run_and_is_reported():
    rise = [(200 + 12 * k, 100, False) for k in range(10)]
    coast = [(305, 100, False), (300, 100, False), (296, 100, False)]
    samples = rise + coast + [(290, 40, False)]
    runs = detect_clipping(*_trace(samples), min_straight_m=100)
    assert len(runs) == 1 and runs[0].end_reason == "lift"


def test_summary_aggregates_clips_and_split_metrics():
    rise = [(240 + 8 * k, 100, False) for k in range(11)]
    clip = [(315, 100, False), (308, 100, False), (300, 100, False), (292, 100, False)]
    runs = detect_clipping(*_trace(rise + clip + [(285, 100, True)]), min_straight_m=100)
    s = summarize_deployment(runs)
    assert s["n_clips"] == 1 and s["total_clip_m"] >= 40 and s["top_speed_kmh"] >= 310
    assert s["total_clip_m"] == s["total_depletion_m"] + s["total_superclip_m"]


def test_lift_ending_run_with_wot_decel_is_a_clip():
    # High-speed WOT deceleration before lift counts; end_reason does not gate is_clip.
    rise = [(240 + 8 * k, 100, False) for k in range(11)]
    fall = [(315, 100, False), (308, 100, False), (300, 100, False), (292, 100, False), (284, 100, False)]
    runs = detect_clipping(*_trace(rise + fall + [(278, 30, False)]), min_straight_m=100)
    assert runs and runs[0].end_reason == "lift" and runs[0].is_clip
    assert runs[0].clip_m >= 40


def test_drag_plateau_is_not_a_clip():
    rise = [(240 + 10 * k, 100, False) for k in range(9)]
    plateau = [(322, 100, False)] * 8 + [(320, 100, False)]
    runs = detect_clipping(*_trace(rise + plateau + [(300, 100, True)]), min_straight_m=100)
    assert runs and not runs[0].is_clip


def test_low_speed_run_is_not_a_clip():
    fast = [(240 + 10 * k, 100, False) for k in range(10)] + [(330, 100, True)]
    slow = [
        (150, 100, False), (165, 100, False), (178, 100, False), (188, 100, False),
        (185, 100, False), (176, 100, False), (168, 100, False), (155, 100, True),
    ]
    d, sp, th, br = _trace(fast + slow, start=0)
    runs = detect_clipping(d, sp, th, br, min_straight_m=100)
    low = [r for r in runs if r.peak_kmh < 250]
    assert low and not low[0].is_clip


def test_ddr_classifies_deploy_depletion_residual():
    """Synthetic lap with known baseline: sharp residual drop above 280 km/h -> depletion clip."""
    n = 80
    d = [i * 25.0 for i in range(n)]
    sp = [180.0 + min(i * 2.2, 120.0) for i in range(n)]
    # plateau then drop at high speed
    for i in range(55, n):
        sp[i] = 310.0 - (i - 55) * 4.0  # steep fall 310 -> 210
    th = [100.0] * n
    br = [False] * n
    br[-1] = True
    _, _, _, _, t = _trace_with_time(list(zip(sp, th, br)), step=25)
    runs = detect_clipping(d, sp, th, br, time_s=t, gear=[8] * n, min_straight_m=200)
    clips = [r for r in runs if r.is_clip]
    assert clips
    assert clips[0].depletion_m + clips[0].superclip_m >= 40


def test_summary_max_severity_is_most_negative():
    rise = [(240 + 8 * k, 100, False) for k in range(11)]
    clip = [(315, 100, False), (308, 100, False), (300, 100, False), (292, 100, False)]
    runs = detect_clipping(*_trace(rise + clip + [(285, 100, True)]), min_straight_m=100)
    s = summarize_deployment(runs)
    if s["n_clips"]:
        assert s["max_clip_severity_ms2"] <= DEPLETION_RESIDUAL_MS2
