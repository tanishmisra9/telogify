from telogify.ingest.segment import Corner, corner_windows, is_clean_lap

GOOD = dict(
    is_accurate=True,
    deleted=False,
    in_out_lap=False,
    track_status="1",
    rainfall=False,
    track_temp=40.0,
    median_track_temp=40.0,
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


def test_excludes_rain_and_temp_swing():
    assert not is_clean_lap(**{**GOOD, "rainfall": True})
    assert not is_clean_lap(**{**GOOD, "track_temp": 50.0})  # 10C above median
    assert is_clean_lap(**{**GOOD, "track_temp": 43.0})  # 3C within tolerance


def test_corner_windows():
    corners = [Corner(1, 200.0), Corner(2, 500.0)]
    assert corner_windows(corners, half_window_m=50.0) == [
        (1, 150.0, 250.0),
        (2, 450.0, 550.0),
    ]
