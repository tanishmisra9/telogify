from telogify.analysis.quali_trace import (
    build_distance_grid,
    delta_to_pole_s,
    fraction_aligned_query,
    is_distance_plausible,
    lap_relative_time_s,
    representative_max_distance_m,
    resample_to_grid,
    resolve_pole_reference,
)


def test_build_distance_grid_covers_zero_to_max_at_fixed_step():
    grid = build_distance_grid(103.0, step_m=10.0)
    assert grid[0] == 0.0 and grid[-1] == 103.0
    assert all(b - a <= 10.0 + 1e-9 for a, b in zip(grid, grid[1:]))


def test_build_distance_grid_zero_max_distance_returns_single_point():
    assert build_distance_grid(0.0) == [0.0]


def test_representative_max_distance_ignores_one_short_outlier():
    # one truncated lap (e.g. a telemetry integration glitch on pole's own lap) among a normal
    # field must not drag the shared grid down to its length -- reproduces 2026 R3 Japan, where
    # pole recorded 5389m against a ~5770-5790m field.
    field = [5389.0, 5772.2, 5773.1, 5773.7, 5783.1, 5785.0, 5797.7]
    assert representative_max_distance_m(field) == 5773.7


def test_representative_max_distance_of_one_lap_is_itself():
    assert representative_max_distance_m([5800.0]) == 5800.0


def test_is_distance_plausible_true_for_normal_line_variance():
    # ~19m short and ~49m long are real, observed racing-line variance -- both must stay plausible
    assert is_distance_plausible(5821.8, 5840.8) is True
    assert is_distance_plausible(5883.6, 5834.7) is True


def test_is_distance_plausible_keeps_monza_pole_within_line_variance():
    # 2026 R13 Italy: Gasly's pole lap recorded +110m (+1.92%) vs a ~5766m field -- a
    # verified-uniform stretch, not a glitch. The flat-100m cap wrongly dropped it and relabelled
    # the runner-up as pole; the 2.5% relative cap keeps it.
    assert is_distance_plausible(5876.1, 5765.7) is True


def test_is_distance_plausible_false_for_telemetry_integration_glitch():
    # ~380m short / -6.6% (2026 R3 Japan pole) is not a racing line, it's corrupted telemetry
    assert is_distance_plausible(5389.0, 5773.7) is False
    # ~224m long / +3.9% (2026 R3 Japan OCO) -- same failure mode, opposite direction
    assert is_distance_plausible(5994.6, 5770.3) is False
    # ~184m long / +3.2% (2026 R13 Italy Sainz)
    assert is_distance_plausible(5949.9, 5765.7) is False


def test_is_distance_plausible_bound_scales_with_lap_length():
    # 120m off is fine on a 6000m lap (2%) but not on a 4000m one (3%)
    assert is_distance_plausible(6120.0, 6000.0) is True
    assert is_distance_plausible(4120.0, 4000.0) is False


def test_is_distance_plausible_boundary_is_inclusive_both_directions():
    assert is_distance_plausible(700.0, 800.0, max_deviation_frac=0.125) is True  # cap = 100m exactly
    assert is_distance_plausible(699.9, 800.0, max_deviation_frac=0.125) is False
    assert is_distance_plausible(900.0, 800.0, max_deviation_frac=0.125) is True
    assert is_distance_plausible(900.1, 800.0, max_deviation_frac=0.125) is False


def test_resolve_pole_reference_uses_official_pole_when_present():
    pole, ref = resolve_pole_reference(["RUS", "GAS", "ANT"], {"RUS": 81.8, "GAS": 81.7, "ANT": 81.9}, "GAS")
    assert pole == "GAS"
    assert ref == "GAS"  # delta measured against the real pole lap


def test_resolve_pole_reference_no_pole_when_official_sitter_has_no_usable_lap():
    # 2026 R3 Japan: Antonelli took pole but his lap telemetry is scrubbed. The chart must NOT
    # call Russell pole -- pole is None, and the delta falls back to the fastest plottable lap.
    pole, ref = resolve_pole_reference(["RUS", "PIA"], {"RUS": 89.076, "PIA": 89.132}, "ANT")
    assert pole is None
    assert ref == "RUS"


def test_resolve_pole_reference_empty_field():
    assert resolve_pole_reference([], {}, "RUS") == (None, None)


def test_resolve_pole_reference_unknown_official_pole_falls_back_to_fastest():
    pole, ref = resolve_pole_reference(["RUS", "PIA"], {"RUS": 89.076, "PIA": 89.132}, None)
    assert pole is None
    assert ref == "RUS"


def test_resample_to_grid_linearly_interpolates_between_samples():
    assert resample_to_grid([0.0, 10.0], [100.0, 200.0], [0.0, 5.0, 10.0]) == [100.0, 150.0, 200.0]


def test_resample_to_grid_empty_input_returns_zeros():
    assert resample_to_grid([], [], [0.0, 5.0, 10.0]) == [0.0, 0.0, 0.0]


def test_resample_to_grid_clamps_outside_recorded_range():
    # fraction-aligned queries never ask past a lap's own range; clamping is only an endpoint guard
    assert resample_to_grid([0.0, 10.0], [100.0, 200.0], [15.0]) == [200.0]


def test_fraction_aligned_query_maps_grid_onto_this_laps_own_length():
    # a lap 10% longer than nominal: nominal grid 0..1000 queries this lap at 0..1100 (0..1 of ITS
    # own length), so the final grid point hits this lap's own finish line, not a nominal meter.
    grid = [0.0, 500.0, 1000.0]
    assert fraction_aligned_query(grid, own_max_distance_m=1100.0, nominal_max_distance_m=1000.0) == [0.0, 550.0, 1100.0]


def test_fraction_aligned_query_is_identity_when_lap_matches_nominal():
    grid = [0.0, 250.0, 500.0]
    assert fraction_aligned_query(grid, own_max_distance_m=500.0, nominal_max_distance_m=500.0) == grid


def test_fraction_alignment_makes_final_delta_the_true_lap_time_gap():
    # the whole point: two laps of different recorded LENGTH but a known time gap must show that
    # exact gap at the final grid point. pole runs 1000m in 30s; trailer runs 1010m in 30.2s.
    grid = build_distance_grid(1005.0, step_m=5.0)  # nominal = field median-ish
    pole_dist, pole_time = [0.0, 1000.0], [0.0, 30.0]
    trail_dist, trail_time = [0.0, 1010.0], [0.0, 30.2]
    pole_on = resample_to_grid(pole_dist, pole_time, fraction_aligned_query(grid, 1000.0, 1005.0))
    trail_on = resample_to_grid(trail_dist, trail_time, fraction_aligned_query(grid, 1010.0, 1005.0))
    delta = delta_to_pole_s(trail_on, pole_on)
    assert round(delta[-1], 6) == 0.2  # exactly the real lap-time gap, not a distance artifact


def test_lap_relative_time_s_starts_at_zero():
    result = lap_relative_time_s([12.3, 12.5, 12.9])
    assert result[0] == 0.0
    assert [round(v, 6) for v in result] == [0.0, 0.2, 0.6]


def test_lap_relative_time_s_empty_input_returns_empty():
    assert lap_relative_time_s([]) == []


def test_delta_to_pole_is_zero_when_driver_is_the_pole_lap_itself():
    time_on_grid = [0.0, 1.2, 2.5, 3.9]
    assert delta_to_pole_s(time_on_grid, time_on_grid) == [0.0, 0.0, 0.0, 0.0]


def test_delta_to_pole_is_positive_when_driver_trails_the_pole():
    pole = [0.0, 1.0, 2.0, 3.0]
    trailing = [0.0, 1.1, 2.3, 3.6]
    deltas = delta_to_pole_s(trailing, pole)
    assert deltas[0] == 0.0
    assert all(d > 0 for d in deltas[1:])
