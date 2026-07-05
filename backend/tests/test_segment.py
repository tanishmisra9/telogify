from telogify.ingest.segment import Corner, corner_windows, is_clean_lap

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
