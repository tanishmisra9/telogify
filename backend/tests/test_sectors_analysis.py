from telogify.analysis.sectors import best_across_sessions, best_top_speeds, sector_dominance


def test_best_across_sessions_keeps_minimum_and_its_session():
    rows = [
        {"driver": "VER", "sector": 1, "best_time_s": 30.5, "session_type": "FP1"},
        {"driver": "VER", "sector": 1, "best_time_s": 29.9, "session_type": "FP2"},
        {"driver": "VER", "sector": 1, "best_time_s": 30.1, "session_type": "FP3"},
    ]
    out = best_across_sessions(rows)
    assert len(out) == 1
    assert out[0].best_time_s == 29.9
    assert out[0].session_type == "FP2"


def test_best_across_sessions_separates_sectors():
    rows = [
        {"driver": "VER", "sector": 1, "best_time_s": 30.0, "session_type": "FP1"},
        {"driver": "VER", "sector": 2, "best_time_s": 40.0, "session_type": "FP1"},
    ]
    out = {b.sector: b.best_time_s for b in best_across_sessions(rows)}
    assert out == {1: 30.0, 2: 40.0}


def test_sector_dominance_ranks_by_constructor_best_with_margin():
    rows = [
        {"sector": 1, "best_time_s": 30.0, "constructor": "Ferrari"},
        {"sector": 1, "best_time_s": 30.5, "constructor": "Mercedes"},
        {"sector": 1, "best_time_s": 29.9, "constructor": "Ferrari"},  # teammate, still Ferrari's best
    ]
    out = sector_dominance(rows)
    assert len(out) == 1
    assert out[0].constructor == "Ferrari"
    assert out[0].best_time_s == 29.9
    assert abs(out[0].margin_s - 0.6) < 1e-9


def test_sector_dominance_no_margin_with_single_constructor():
    rows = [{"sector": 1, "best_time_s": 30.0, "constructor": "Ferrari"}]
    out = sector_dominance(rows)
    assert out[0].margin_s is None


def test_sector_dominance_ignores_rows_without_constructor():
    rows = [{"sector": 1, "best_time_s": 30.0, "constructor": None}]
    assert sector_dominance(rows) == []


def test_best_top_speeds_picks_max_across_zones_and_sessions():
    rows = [
        {"driver": "VER", "session_type": "FP1", "max_speed_kmh": 320.0},
        {"driver": "VER", "session_type": "FP2", "max_speed_kmh": 325.0},
        {"driver": "VER", "session_type": "FP1", "max_speed_kmh": 310.0},
    ]
    out = {b["driver"]: b for b in best_top_speeds(rows)}
    assert out["VER"]["max_speed_kmh"] == 325.0
    assert out["VER"]["session_type"] == "FP2"
