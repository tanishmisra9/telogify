from telogify.analysis.quali_trace import (
    build_distance_grid,
    delta_to_pole_s,
    lap_relative_time_s,
    resample_to_grid,
)


def test_build_distance_grid_covers_zero_to_max_at_fixed_step():
    grid = build_distance_grid(103.0, step_m=10.0)
    assert grid[0] == 0.0 and grid[-1] == 103.0
    assert all(b - a <= 10.0 + 1e-9 for a, b in zip(grid, grid[1:]))


def test_build_distance_grid_zero_max_distance_returns_single_point():
    assert build_distance_grid(0.0) == [0.0]


def test_resample_to_grid_linearly_interpolates_between_samples():
    assert resample_to_grid([0.0, 10.0], [100.0, 200.0], [0.0, 5.0, 10.0]) == [100.0, 150.0, 200.0]


def test_resample_to_grid_empty_input_returns_zeros():
    assert resample_to_grid([], [], [0.0, 5.0, 10.0]) == [0.0, 0.0, 0.0]


def test_resample_to_grid_clamps_outside_recorded_range():
    # grid point past the last recorded distance holds at the last recorded value
    assert resample_to_grid([0.0, 10.0], [100.0, 200.0], [15.0]) == [200.0]


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
