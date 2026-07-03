from telogify.ingest.sectors import best_sectors


def test_best_sectors_picks_minimum_per_driver_per_sector():
    rows = [
        {"driver": "VER", "sector1_s": 30.1, "sector2_s": 40.2, "sector3_s": None},
        {"driver": "VER", "sector1_s": 29.9, "sector2_s": None, "sector3_s": 20.0},
    ]
    out = {(b.driver, b.sector): b.best_time_s for b in best_sectors(rows)}
    assert out[("VER", 1)] == 29.9
    assert out[("VER", 2)] == 40.2
    assert out[("VER", 3)] == 20.0


def test_best_sectors_skips_missing_sector_times():
    rows = [{"driver": "LEC", "sector1_s": None, "sector2_s": None, "sector3_s": None}]
    assert best_sectors(rows) == []


def test_best_sectors_excludes_deleted_laps():
    # The deleted lap holds a faster sector 1 (track-limits), but must not win.
    rows = [
        {"driver": "VER", "sector1_s": 30.0, "sector2_s": None, "sector3_s": None},
        {"driver": "VER", "sector1_s": 29.0, "sector2_s": None, "sector3_s": None, "deleted": True},
    ]
    out = {(b.driver, b.sector): b.best_time_s for b in best_sectors(rows)}
    assert out[("VER", 1)] == 30.0


def test_best_sectors_separates_drivers():
    rows = [
        {"driver": "VER", "sector1_s": 30.0, "sector2_s": None, "sector3_s": None},
        {"driver": "LEC", "sector1_s": 29.5, "sector2_s": None, "sector3_s": None},
    ]
    out = {b.driver: b.best_time_s for b in best_sectors(rows)}
    assert out == {"VER": 30.0, "LEC": 29.5}
