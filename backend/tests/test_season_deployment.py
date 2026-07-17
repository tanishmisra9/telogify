"""Tests for the season deployment power-unit metrics module (pure, no DB)."""

from telogify.analysis.season_deployment import (
    MIN_BIN_N,
    PU_GROUPS,
    PuGroup,
    bin_by_speed,
    measure_group,
    rank_groups_best_to_worst,
)


def test_bin_by_speed_groups_by_10kmh_bucket():
    points = [(151.0, 1.0), (155.0, 3.0), (250.0, -2.0)]
    bins = bin_by_speed(points)
    assert len(bins) == 2
    assert bins[0].speed_mid == 155.0
    assert bins[0].median_accel == 2.0  # median of 1.0, 3.0
    assert bins[0].n == 2
    assert bins[1].speed_mid == 255.0
    assert bins[1].n == 1


def test_bin_by_speed_sorted_by_speed():
    points = [(280.0, 0.0), (150.0, 0.0), (210.0, 0.0)]
    bins = bin_by_speed(points)
    assert [b.speed_mid for b in bins] == sorted(b.speed_mid for b in bins)


def _scatter_for(team: str, punch_accel: float, hold_accel: float) -> list[list[float]]:
    """MIN_BIN_N points per bin, punch band flat at punch_accel, hold band flat at hold_accel."""
    points = []
    for speed in (255.0, 265.0):  # two punch-band bins (250-290)
        points.extend([[speed, punch_accel]] * MIN_BIN_N)
    for speed in (295.0, 305.0):  # two hold-band bins (>= 290)
        points.extend([[speed, hold_accel]] * MIN_BIN_N)
    return points


def test_measure_group_computes_punch_and_hold():
    group = PuGroup("TestPU", "TestTeam", ("TestTeam",))
    scatter = {"TestTeam": _scatter_for("TestTeam", 1.5, -1.5)}
    m = measure_group(group, scatter)
    assert m.teams == ["TestTeam"]
    assert m.punch == 1.5
    assert m.hold == -1.5
    assert m.fade == 3.0


def test_measure_group_pools_multiple_teams():
    group = PuGroup("TestPU", "A", ("A", "B"))
    scatter = {
        "A": _scatter_for("A", 1.0, -1.0),
        "B": _scatter_for("B", 2.0, -2.0),
    }
    m = measure_group(group, scatter)
    assert set(m.teams) == {"A", "B"}
    # median of pooled bin medians across the two teams' identical-speed bins
    assert m.punch is not None


def test_measure_group_none_when_bins_too_thin():
    group = PuGroup("TestPU", "A", ("A",))
    # Only 2 points per bin, below MIN_BIN_N=5: the bin itself is discarded.
    scatter = {"A": [[255.0, 1.0], [255.0, 1.2]]}
    m = measure_group(group, scatter)
    assert m.punch is None
    assert m.hold is None
    assert m.fade is None


def test_measure_group_absent_team_not_counted():
    group = PuGroup("TestPU", "A", ("A", "B"))
    scatter = {"A": _scatter_for("A", 1.0, -1.0)}  # B has no data this season
    m = measure_group(group, scatter)
    assert m.teams == ["A"]


def test_rank_groups_best_to_worst_orders_by_punch_then_hold():
    scatter = {
        "Mercedes": _scatter_for("Mercedes", 1.0, -1.0),
        "Ferrari": _scatter_for("Ferrari", 2.0, -0.5),  # best punch
        "Red Bull Racing": _scatter_for("Red Bull Racing", 1.0, -3.0),  # ties Mercedes on punch, worse hold
    }
    ranked = rank_groups_best_to_worst(scatter)
    names = [m.group.name for m in ranked]
    assert names[0] == "Ferrari"  # highest punch wins outright
    assert names[1] == "Mercedes"  # punch tie with Red Bull, but better hold
    assert names[2] == "Red Bull"


def test_rank_groups_skips_groups_with_no_data_at_all():
    scatter = {"Mercedes": _scatter_for("Mercedes", 1.0, -1.0)}
    ranked = rank_groups_best_to_worst(scatter)
    assert [m.group.name for m in ranked] == ["Mercedes"]


def test_rank_groups_empty_scatter_returns_empty():
    assert rank_groups_best_to_worst({}) == []


def test_pu_groups_cover_2026_supply_map():
    names = {g.name for g in PU_GROUPS}
    assert names == {"Mercedes", "Ferrari", "Red Bull", "Honda", "Audi"}
    all_teams = {t for g in PU_GROUPS for t in g.teams}
    assert "Ferrari" in all_teams and "Aston Martin" in all_teams


if __name__ == "__main__":
    # ponytail: smallest runnable check for the ranking logic without a test framework.
    scatter = {
        "Mercedes": _scatter_for("Mercedes", 1.0, -1.0),
        "Ferrari": _scatter_for("Ferrari", 2.0, -0.5),
    }
    ranked = rank_groups_best_to_worst(scatter)
    assert ranked[0].group.name == "Ferrari"
    print("season_deployment demo OK")
