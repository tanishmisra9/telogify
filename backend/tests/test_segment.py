import types

import pandas as pd
import pytest

from telogify.ingest import quali_character
from telogify.ingest.segment import (
    Corner,
    corner_windows,
    is_clean_lap,
    lap_rainfall,
    select_clean_laps,
)

GOOD = dict(
    is_accurate=True,
    deleted=False,
    in_out_lap=False,
    track_status="1",
    rainfall=False,
)


def test_clean_lap_accepts_green_dry_lap():
    assert is_clean_lap(**GOOD)


def test_excludes_safety_car_and_vsc_and_yellow():
    assert not is_clean_lap(**{**GOOD, "track_status": "4"})  # SC
    assert not is_clean_lap(**{**GOOD, "track_status": "6"})  # VSC
    assert not is_clean_lap(**{**GOOD, "track_status": "2"})  # yellow
    assert not is_clean_lap(**{**GOOD, "track_status": "12"})  # clear then yellow


def test_excludes_in_out_inaccurate_deleted():
    assert not is_clean_lap(**{**GOOD, "in_out_lap": True})
    assert not is_clean_lap(**{**GOOD, "is_accurate": False})
    assert not is_clean_lap(**{**GOOD, "deleted": True})


def test_excludes_rain():
    assert not is_clean_lap(**{**GOOD, "rainfall": True})


def test_corner_windows():
    corners = [Corner(1, 200.0), Corner(2, 500.0)]
    assert corner_windows(corners, half_window_m=50.0) == [
        (1, 150.0, 250.0),
        (2, 450.0, 550.0),
    ]


def test_corner_windows_default_half_window():
    from telogify.ingest.segment import CORNER_HALF_WINDOW_M

    corners = [Corner(3, 1000.0)]
    lo, hi = corner_windows(corners)[0][1:]
    assert hi - lo == 2 * CORNER_HALF_WINDOW_M


# --- lap_rainfall / the selectors' weather lookup -----------------------------------------------
# FastF1's `Laps.get_weather_data()` returns an all-NaN row for a lap that ends before the first
# weather sample, then casts the whole frame back to the weather dtypes (WindDirection is int64),
# so ONE such lap raised "cannot convert float NaN to integer" for the entire session. Mexico City
# 2026 FP3 is the real case: first weather sample at 46.7 s, 18 laps ended before it.

def _td(seconds: float) -> pd.Timedelta:
    return pd.Timedelta(seconds=seconds)


def _weather(*samples: tuple[float, bool]) -> pd.DataFrame:
    """(session_seconds, rainfall) samples, FastF1-shaped (the columns lap_rainfall may touch)."""
    return pd.DataFrame(
        {
            "Time": [_td(s) for s, _ in samples],
            "Rainfall": [r for _, r in samples],
            "WindDirection": [100] * len(samples),  # int64, the column that made FastF1 crash
        }
    )


def _laps(*spans: tuple[float, float]) -> pd.DataFrame:
    """(start_s, end_s) laps with the columns both selectors read."""
    n = len(spans)
    return pd.DataFrame(
        {
            "Driver": ["VER"] * n,
            "LapStartTime": [_td(a) for a, _ in spans],
            "Time": [_td(b) for _, b in spans],
            "IsAccurate": [True] * n,
            "Deleted": [False] * n,
            "PitInTime": [pd.NaT] * n,
            "PitOutTime": [pd.NaT] * n,
            "TrackStatus": ["1"] * n,
        }
    )


def test_lap_rainfall_laps_ending_before_the_first_sample_do_not_raise():
    # The Mexico FP3 shape: samples start at 46.7 s, the first laps end at 20 s and 40 s.
    laps = _laps((0, 20), (20, 40), (40, 100))
    assert lap_rainfall(laps, _weather((46.7, False), (106.7, False))) == [False, False, False]


def test_lap_rainfall_early_laps_take_the_earliest_sample():
    # If the earliest sample says rain, laps run before any sample existed count as wet.
    laps = _laps((0, 20), (20, 40), (200, 280))
    assert lap_rainfall(laps, _weather((46.7, True), (106.7, True), (166.7, False))) == [True, True, False]


def test_lap_rainfall_prefers_the_first_sample_inside_the_lap():
    laps = _laps((100, 200))
    # samples at 120 (dry) and 160 (wet) are both inside; FastF1 takes the first.
    assert lap_rainfall(laps, _weather((60, True), (120, False), (160, True))) == [False]


def test_lap_rainfall_falls_back_to_the_last_sample_before_the_lap_ends():
    laps = _laps((100, 200))
    # nothing inside (100, 200): the last sample at or before 200 is the wet one at 90
    assert lap_rainfall(laps, _weather((30, False), (90, True), (260, False))) == [True]


def test_lap_rainfall_sample_exactly_on_a_lap_boundary_counts_as_inside():
    laps = _laps((100, 200))
    assert lap_rainfall(laps, _weather((100, True), (150, False))) == [True]
    assert lap_rainfall(laps, _weather((50, False), (200, True))) == [True]


def test_lap_rainfall_without_a_weather_table_is_dry_not_nan():
    # bool(NaN) is True: a NaN here would mark every lap wet and leave no clean laps at all.
    assert lap_rainfall(_laps((0, 80), (80, 160)), _weather()) == [False, False]


def test_lap_rainfall_lap_without_an_end_time_takes_the_earliest_sample():
    laps = _laps((0, 80), (80, 160))
    laps.loc[1, "Time"] = pd.NaT
    assert lap_rainfall(laps, _weather((10, False), (100, True))) == [False, False]


def test_lap_rainfall_unsorted_weather_is_handled():
    laps = _laps((100, 200))
    assert lap_rainfall(laps, _weather((160, True), (30, False), (120, False))) == [False]


def test_lap_rainfall_matches_fastf1_wherever_fastf1_works():
    """Healthy sessions must be unchanged: same answer as FastF1's own lookup on every lap that
    has weather data (so only the crashing case differs)."""
    from fastf1.core import Laps

    weather = _weather((30, False), (90, True), (150, True), (210, False), (270, False))
    spans = [(40, 80), (80, 130), (130, 190), (190, 215), (215, 300), (270, 330)]
    laps = _laps(*spans)
    session = types.SimpleNamespace(weather_data=weather)
    theirs = Laps(laps, session=session).get_weather_data()["Rainfall"].astype(bool).tolist()
    assert lap_rainfall(laps, weather) == theirs


def _session(laps: pd.DataFrame, weather: pd.DataFrame) -> types.SimpleNamespace:
    return types.SimpleNamespace(laps=laps, weather_data=weather)


@pytest.mark.parametrize("selector", [select_clean_laps, quali_character.select_representative_laps])
def test_selectors_survive_laps_before_the_first_weather_sample(selector):
    # Both selectors crashed on this; neither had a test. Lap 1 predates the first sample.
    laps = _laps((0, 40), (40, 120), (120, 200))
    kept = selector(_session(laps, _weather((46.7, False), (106.7, False), (166.7, False))))
    assert list(kept.index) == [0, 1, 2]


@pytest.mark.parametrize("selector", [select_clean_laps, quali_character.select_representative_laps])
def test_selectors_drop_a_wet_lap_and_keep_dry_ones(selector):
    laps = _laps((0, 40), (40, 120), (120, 200))
    weather = _weather((46.7, False), (106.7, False), (130.0, True))  # rain from 130 s
    # lap 3 (120-200): first sample inside is the wet one at 130 s
    assert list(selector(_session(laps, weather)).index) == [0, 1]


@pytest.mark.parametrize("selector", [select_clean_laps, quali_character.select_representative_laps])
def test_selectors_still_apply_the_other_lap_filters(selector):
    laps = _laps((0, 40), (40, 120))
    laps.loc[1, "Deleted"] = True
    assert list(selector(_session(laps, _weather((10, False)))).index) == [0]
