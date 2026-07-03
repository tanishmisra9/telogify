import pytest

from telogify.analysis.degradation import (
    fit_all_groups,
    fit_group,
    least_squares_fit,
    theil_sen_fit,
)


def test_least_squares_fit_recovers_known_line():
    xs = [0, 1, 2, 3, 4]
    ys = [90.0, 90.1, 90.2, 90.3, 90.4]
    slope, intercept = least_squares_fit(xs, ys)
    assert abs(slope - 0.1) < 1e-9
    assert abs(intercept - 90.0) < 1e-9


def test_theil_sen_recovers_known_line():
    xs = [0, 1, 2, 3, 4]
    ys = [90.0 + 0.1 * x for x in xs]
    slope, intercept = theil_sen_fit(xs, ys)
    assert abs(slope - 0.1) < 1e-9
    assert abs(intercept - 90.0) < 1e-9


def test_theil_sen_none_below_two_points_or_no_distinct_x():
    assert theil_sen_fit([1.0], [90.0]) is None
    assert theil_sen_fit([5.0, 5.0, 5.0], [90.0, 91.0, 92.0]) is None


def test_theil_sen_resists_outlier_lap_that_drags_ols():
    # A clean 0.10 s/lap ramp with one traffic-ruined lap (+3s at age 3).
    xs = [0, 1, 2, 3, 4, 5, 6, 7]
    ys = [90.0 + 0.1 * x for x in xs]
    ys[3] += 6.0  # one lock-up / off-track lap
    ts_slope, _ = theil_sen_fit(xs, ys)
    ols_slope, _ = least_squares_fit(xs, ys)
    # Theil-Sen stays near the true 0.10; OLS is dragged well off it.
    assert abs(ts_slope - 0.1) < 0.02
    assert abs(ols_slope - 0.1) > 0.05


def test_least_squares_fit_none_below_two_points():
    assert least_squares_fit([1.0], [90.0]) is None
    assert least_squares_fit([], []) is None


def test_least_squares_fit_none_with_zero_variance_x():
    """Same tyre age for every lap: no line to fit."""
    assert least_squares_fit([5.0, 5.0, 5.0], [90.0, 91.0, 92.0]) is None


def test_fit_group_computes_cost_at_reference_age():
    ages = list(range(15))
    times = [90.0 + 0.1 * a for a in ages]
    fit = fit_group("Ferrari", "MEDIUM", ages, times, reference_age=13)
    assert abs(fit.slope_s_per_lap - 0.1) < 1e-9
    assert abs(fit.cost_at_reference_s - 1.3) < 1e-9
    assert fit.n_laps == 15


def test_fit_group_none_below_min_laps():
    ages = [1.0, 2.0]
    times = [90.0, 90.1]
    assert fit_group("Ferrari", "MEDIUM", ages, times, min_laps=5) is None


def test_fit_all_groups_flags_slope_far_above_field_median():
    rows = []
    for age in range(15):
        rows.append({"constructor": "Ferrari", "compound": "MEDIUM", "tyre_age": age, "lap_time_s": 90.0 + 0.20 * age})
        rows.append({"constructor": "Mercedes", "compound": "MEDIUM", "tyre_age": age, "lap_time_s": 90.0 + 0.02 * age})
        rows.append({"constructor": "McLaren", "compound": "MEDIUM", "tyre_age": age, "lap_time_s": 90.0 + 0.03 * age})

    fits = {f.constructor: f for f in fit_all_groups(rows)}
    assert fits["Ferrari"].flagged is True
    assert fits["Mercedes"].flagged is False
    assert fits["McLaren"].flagged is False


def test_fit_all_groups_ignores_rows_missing_age_or_time():
    rows = [
        {"constructor": "A", "compound": "SOFT", "tyre_age": None, "lap_time_s": 90.0},
        {"constructor": "A", "compound": "SOFT", "tyre_age": 1.0, "lap_time_s": None},
    ]
    assert fit_all_groups(rows) == []


def test_fit_all_groups_negative_slope_not_flagged_and_excluded_from_field_median():
    rows = []
    for age in range(6):
        # Team improving with age (negative slope): should never be flagged.
        rows.append({"constructor": "Odd", "compound": "SOFT", "tyre_age": age, "lap_time_s": 90.0 - 0.05 * age})
    fits = fit_all_groups(rows)
    assert len(fits) == 1
    assert fits[0].flagged is False


@pytest.mark.parametrize("n", [0, 1, 2, 3, 4])
def test_fit_group_requires_min_laps_boundary(n):
    ages = list(range(n))
    times = [90.0 + a for a in ages]
    assert fit_group("A", "SOFT", ages, times, min_laps=5) is None
