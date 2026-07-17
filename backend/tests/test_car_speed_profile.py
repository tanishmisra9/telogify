from telogify.analysis.car_speed_profile import CornerReading, summarize_speed_profile


def test_groups_confident_corners_by_speed_class():
    corners = [
        CornerReading(1, "low", 3.0, 0.8),
        CornerReading(2, "low", 5.0, 0.7),
        CornerReading(7, "high", -2.0, 0.9),
    ]
    result = summarize_speed_profile(corners, None, None, {}, {})
    by_class = {c["speed_class"]: c for c in result["cornering_by_speed_class"]}
    assert by_class["low"]["n_corners"] == 2
    assert abs(by_class["low"]["avg_delta_kmh"] - 4.0) < 1e-9
    assert by_class["low"]["corner_numbers"] == [1, 2]
    assert by_class["high"]["avg_delta_kmh"] == -2.0
    assert result["confident"] is True


def test_drops_low_confidence_corner():
    corners = [CornerReading(1, "low", 3.0, 0.2)]
    result = summarize_speed_profile(corners, None, None, {}, {})
    assert result["cornering_by_speed_class"] == []
    assert result["confident"] is False


def test_drops_artifact_sized_corner_delta():
    corners = [CornerReading(1, "low", 20.0, 0.9)]  # above CORNER_ARTIFACT_KMH
    result = summarize_speed_profile(corners, None, None, {}, {})
    assert result["cornering_by_speed_class"] == []


def test_top_speed_delta_within_threshold():
    result = summarize_speed_profile([], 330.0, 325.0, {}, {})
    assert result["top_speed_delta_kmh"] == 5.0
    assert result["confident"] is True


def test_top_speed_delta_dropped_as_artifact():
    result = summarize_speed_profile([], 330.0, 300.0, {}, {})  # 30 km/h, above threshold
    assert result["top_speed_delta_kmh"] is None
    assert result["confident"] is False


def test_top_speed_delta_none_when_either_missing():
    result = summarize_speed_profile([], 330.0, None, {}, {})
    assert result["top_speed_delta_kmh"] is None


def test_sector_deltas_only_for_shared_sectors():
    result = summarize_speed_profile([], None, None, {1: 28.1, 2: 30.5}, {1: 28.4})
    assert result["sector_deltas_s"] == [{"sector": 1, "delta_s": -0.3}]
    assert result["confident"] is True


def test_all_empty_is_not_confident():
    result = summarize_speed_profile([], None, None, {}, {})
    assert result == {
        "cornering_by_speed_class": [],
        "top_speed_delta_kmh": None,
        "sector_deltas_s": [],
        "confident": False,
    }
