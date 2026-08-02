"""Tests for the measured Gmail iOS dark-mode transform and CSS support matrix.

These modules hold real measured data (captured 2026-08-01, see each module's docstring), not
guessed formulas or emulation. Tests here check the lookup/fitting machinery around that data,
not the data's real-world accuracy -- that accuracy is bounded and reported by
held_out_residual, not asserted as a pass/fail threshold.
"""

import pytest

from telogify.emailsim.darkmode import DARK_MODE_SAMPLES, ColorTransform, held_out_residual
from telogify.emailsim.support import GMAIL_IOS_SUPPORT, supported


def test_color_transform_returns_exact_measured_result_for_a_sampled_input():
    transform = ColorTransform.fit()
    # #000000 was directly measured -> #ffffff; querying the exact sampled input must return
    # exactly what was measured, not some averaged/interpolated neighbor.
    assert transform.apply("#000000") == "#ffffff"
    assert transform.nearest_sample_distance("#000000") == 0.0


def test_color_transform_every_sample_round_trips_to_itself():
    transform = ColorTransform.fit()
    for input_hex, dark_hex in DARK_MODE_SAMPLES.items():
        assert transform.apply(input_hex) == dark_hex


def test_color_transform_nearest_sample_distance_grows_for_unmeasured_colors():
    transform = ColorTransform.fit()
    # a color identical to a sample has distance 0; a wildly different one should not.
    assert transform.nearest_sample_distance("#0a0a0a") == 0.0
    assert transform.nearest_sample_distance("#123456") > 0.0


def test_color_transform_fit_accepts_a_custom_sample_dict():
    custom = {"#ff0000": "#00ff00"}
    transform = ColorTransform.fit(custom)
    assert transform.apply("#ff0000") == "#00ff00"
    # any other input still resolves to the single available sample (nearest neighbor of one).
    assert transform.apply("#fe0101") == "#00ff00"


def test_held_out_residual_is_a_non_negative_finite_number():
    residual = held_out_residual()
    assert residual >= 0
    assert residual < 442  # max possible Euclidean distance in 8-bit RGB space (sqrt(3*255^2))


def test_held_out_residual_is_deterministic_for_a_fixed_seed():
    assert held_out_residual(seed=1) == held_out_residual(seed=1)


def test_gmail_ios_support_covers_every_probe_b_test_id():
    # Superset, not equality: GMAIL_IOS_SUPPORT also carries measured results from standalone
    # one-off probes (e.g. clip_path) that were never added to the formal probe_b_tests() suite,
    # so every formal test must have a verdict, but the matrix may legitimately have more.
    from telogify.emailsim.probe import probe_b_tests

    ids = {t.id for t in probe_b_tests()}
    assert ids <= set(GMAIL_IOS_SUPPORT)


def test_supported_returns_bool_for_known_id():
    assert supported("display_flex") is True
    assert supported("display_grid") is False


def test_supported_raises_on_unknown_id():
    with pytest.raises(KeyError):
        supported("not_a_real_test")
