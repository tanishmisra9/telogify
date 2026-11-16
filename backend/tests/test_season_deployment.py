"""Tests for the season deployment power-unit metrics module (pure, no DB)."""

from telogify.analysis.season_deployment import (
    MIN_BIN_N,
    PU_GROUPS,
    PuGroup,
    bin_by_speed,
    build_ranking,
    measure_group,
    package_form,
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


def test_rank_groups_best_to_worst_orders_by_average_of_punch_and_hold():
    scatter = {
        # Highest punch (2.0) but the weakest hold (-2.0): avg = 0.0.
        "Mercedes": _scatter_for("Mercedes", 2.0, -2.0),
        # Lowest punch (1.0) but by far the best hold (+1.0): avg = 1.0, wins outright.
        # Proves the average decides it, not punch alone (a punch-only ranking would put
        # this group last).
        "Ferrari": _scatter_for("Ferrari", 1.0, 1.0),
        # Middling on both: avg = 0.5.
        "Red Bull Racing": _scatter_for("Red Bull Racing", 1.5, -0.5),
    }
    ranked = rank_groups_best_to_worst(scatter)
    names = [m.group.name for m in ranked]
    assert names == ["Ferrari", "Red Bull", "Mercedes"]


def test_rank_groups_falls_back_to_the_known_band_when_only_one_is_measured():
    # Mercedes: only punch measurable this season (e.g. too few laps deep into the top-speed
    # band yet); its score should fall back to that punch value, not drop to None.
    only_punch = [[255.0, 3.0]] * MIN_BIN_N + [[265.0, 3.0]] * MIN_BIN_N
    scatter = {
        "Mercedes": only_punch,
        "Ferrari": _scatter_for("Ferrari", 1.0, 1.0),  # avg = 1.0, below Mercedes' 3.0
    }
    ranked = rank_groups_best_to_worst(scatter)
    assert [m.group.name for m in ranked] == ["Mercedes", "Ferrari"]
    assert ranked[0].punch == 3.0 and ranked[0].hold is None


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


# --- per-round form + the ranking table -------------------------------------------------

def _round(punch: dict[str, float], hold: dict[str, float | None] | None = None) -> dict[str, list[list[float]]]:
    """One round's scatter keyed by each PU's works team. hold=None for a team drops the hold band."""
    hold = hold or {t: 0.0 for t in punch}
    out = {}
    for team, p in punch.items():
        pts = _scatter_for(team, p, hold[team] if hold[team] is not None else 0.0)
        if hold[team] is None:
            pts = [pt for pt in pts if pt[0] < 290]
        out[team] = pts
    return out


def test_package_form_gains_for_a_power_unit_that_improves_late():
    # Ferrari leads big early (Mercedes gap 1.0), Mercedes leads narrowly late (Ferrari gap 0.8): over the whole
    # season Ferrari is ahead (flat means 0.5 vs 0.4), on recent form Mercedes is, so Mercedes gains a place.
    by_round = {}
    for r in range(1, 9):
        late = r > 4
        by_round[r] = _round({"Mercedes": 3.0 if late else 1.0, "Ferrari": 1.4 if late else 3.0, "Audi": 0.0})
    form = package_form(by_round, current_round=8)
    assert form["Mercedes"]["form_places"] > 0
    assert form["Ferrari"]["form_places"] < 0


def test_package_form_none_below_min_rounds():
    by_round = {r: _round({"Mercedes": 2.0, "Ferrari": 1.0}) for r in range(1, 4)}  # 3 < MIN_ROUNDS_FOR_FORM
    form = package_form(by_round, current_round=3)
    assert form["Mercedes"]["form_places"] is None


def test_package_form_skips_a_round_where_the_bands_differ_from_the_best():
    # Round 1: Ferrari only has the punch band, Mercedes (the best) has both: Ferrari is not compared that round.
    by_round = {1: _round({"Mercedes": 2.0, "Ferrari": 1.0}, {"Mercedes": 0.0, "Ferrari": None})}
    by_round.update({r: _round({"Mercedes": 2.0, "Ferrari": 1.0}) for r in range(2, 6)})
    form = package_form(by_round, current_round=5)
    # Ferrari's flat mean is over rounds 2-5 only (4 rounds, so the arrow exists); had round 1 counted
    # it would be a 5-value mean including a score built on punch alone.
    assert form["Ferrari"]["form_places"] is not None
    assert package_form({1: by_round[1]}, 1).get("Ferrari") is None


def test_build_ranking_orders_best_first_and_gap_is_to_the_best():
    scatter = {"Mercedes": _scatter_for("Mercedes", 2.0, 0.0), "Ferrari": _scatter_for("Ferrari", 1.0, 0.0)}
    by_round = {r: scatter for r in range(1, 6)}
    ranking = build_ranking(scatter, by_round)
    assert [r["pu"] for r in ranking] == ["Mercedes", "Ferrari"]
    assert ranking[0]["rank"] == 1 and ranking[0]["gap"] == 0
    assert ranking[1]["gap"] == 0.5  # package = mean(punch, hold): 1.0 vs 0.5
    assert ranking[1]["form_places"] == 0  # same order every round: no movement


def test_build_ranking_shows_no_gap_for_a_score_from_a_different_band_set():
    scatter = {
        "Mercedes": _scatter_for("Mercedes", 2.0, 0.0),
        "Ferrari": [pt for pt in _scatter_for("Ferrari", 0.5, 0.0) if pt[0] < 290],  # punch band only
    }
    ranking = {r["pu"]: r for r in build_ranking(scatter, {1: scatter})}
    assert ranking["Mercedes"]["gap"] == 0
    assert ranking["Ferrari"]["gap"] is None and ranking["Ferrari"]["rank"] == 2


def test_build_ranking_empty_without_data():
    assert build_ranking({}, {}) == []


if __name__ == "__main__":
    # ponytail: smallest runnable check for the ranking logic without a test framework.
    scatter = {
        "Mercedes": _scatter_for("Mercedes", 1.0, -1.0),
        "Ferrari": _scatter_for("Ferrari", 2.0, -0.5),
    }
    ranked = rank_groups_best_to_worst(scatter)
    assert ranked[0].group.name == "Ferrari"
    print("season_deployment demo OK")
