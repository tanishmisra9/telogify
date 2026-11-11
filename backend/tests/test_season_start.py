import pytest
from sqlmodel import Session

from telogify.analysis.season_deployment import pu_map_applies
from telogify.analysis.season_start import MIN_ROUNDS_FOR_FORM, build_season_start, build_view, round_gaps
from telogify.models import RaceStart, RaceWeekend
from telogify.models import Session as SessionRow


def car(team, a, b=None):
    return {"constructor": team, "t_0_100_s": a, "t_0_200_s": b}


IDENT = lambda c: c  # noqa: E731


def test_round_gaps_uses_the_median_of_each_teams_cars_and_gaps_to_the_best():
    cars = [car("A", 2.4, 4.4), car("A", 2.6, 4.6), car("B", 2.5, 4.8)]  # A median 4.5, B 4.8
    metric, g = round_gaps(cars, IDENT)
    assert metric == 200
    assert g["A"]["gap_pct"] == pytest.approx(0.0)
    assert g["B"]["gap_s"] == pytest.approx(0.3)
    assert g["B"]["gap_pct"] == pytest.approx(0.3 / 4.5 * 100)
    assert g["A"]["n_cars"] == 2


def test_round_without_any_0_200_time_falls_back_to_0_100():
    metric, g = round_gaps([car("A", 2.6), car("B", 2.9)], IDENT)
    assert metric == 100
    assert g["B"]["gap_s"] == pytest.approx(0.3)


def test_in_a_200_round_a_car_without_a_0_200_time_is_left_out():
    _, g = round_gaps([car("A", 2.4, 4.5), car("A", 2.5, None), car("B", 2.6, 4.9)], IDENT)
    assert g["A"]["n_cars"] == 1


def test_an_unmapped_constructor_is_left_out_not_guessed():
    _, g = round_gaps([car("A", 2.4, 4.5), car("Z", 2.0, 4.0)], lambda c: None if c == "Z" else c)
    assert set(g) == {"A"}


def _season(rows_by_round):
    """rows_by_round: {round: [(team, t100, t200)]}"""
    return [(r, [car(t, a, b) for t, a, b in cars]) for r, cars in sorted(rows_by_round.items())]


def test_pooled_power_unit_median_is_the_median_of_all_its_cars_not_of_team_medians():
    cars = [car("T1", 2.4, 4.4), car("T1", 2.4, 4.4), car("T2", 2.4, 5.4), car("Other", 2.4, 4.8)]
    pu = {"T1": "X", "T2": "X", "Other": "Y"}.get
    _, g = round_gaps(cars, pu)
    # X pooled: 4.4, 4.4, 5.4 -> median 4.4 (team medians 4.4 and 5.4 would average to 4.9)
    assert g["X"]["gap_s"] == pytest.approx(0.0)
    assert g["Y"]["gap_s"] == pytest.approx(0.4)


def test_fallback_rounds_are_plotted_but_excluded_from_the_weighted_and_flat_gaps():
    rounds = _season(
        {
            1: [("A", 2.4, 4.4), ("B", 2.5, 4.84)],  # B +10%
            2: [("A", 2.4, None), ("B", 3.6, None)],  # 0-100 only: B +50% (a different scale)
            3: [("A", 2.4, 4.4), ("B", 2.5, 4.84)],
            4: [("A", 2.4, 4.4), ("B", 2.5, 4.84)],
            5: [("A", 2.4, 4.4), ("B", 2.5, 4.84)],
        }
    )
    rows = {r["key"]: r for r in build_view(rounds, IDENT, {}, 5)}
    b = rows["B"]
    assert [p["round"] for p in b["points"]] == [1, 2, 3, 4, 5]  # the fallback round IS plotted
    assert [p["metric"] for p in b["points"]] == [200, 100, 200, 200, 200]
    assert b["n_rounds"] == 4
    assert b["flat_gap_pct"] == pytest.approx(10.0)  # not dragged up by the +50% fallback point


def test_a_season_with_no_0_200_round_still_ranks_on_what_it_has():
    rounds = _season({1: [("A", 2.4, None), ("B", 2.6, None)], 2: [("A", 2.4, None), ("B", 2.7, None)]})
    rows = {r["key"]: r for r in build_view(rounds, IDENT, {}, 2)}
    assert rows["B"]["n_rounds"] == 2 and rows["B"]["weighted_gap_pct"] > 0


def test_recency_weighting_and_rank_movement():
    # Rounds 1-4: B is 12% behind A. Rounds 5-6: A is 20% behind B.
    # Flat season mean: A 6.7%, B 8.0% -> A ahead. Recency-weighted (half-life 6): A 8.3%, B 7.1% -> B ahead.
    early = [("A", 2.4, 4.4), ("B", 2.4, 4.4 * 1.12)]
    late = [("A", 2.4, 4.4 * 1.2), ("B", 2.4, 4.4)]
    rounds = _season({1: early, 2: early, 3: early, 4: early, 5: late, 6: late})
    rows = {r["key"]: r for r in build_view(rounds, IDENT, {}, 6)}
    a, b = rows["A"], rows["B"]
    assert a["flat_gap_pct"] < b["flat_gap_pct"]  # A ahead over the whole season
    assert b["weighted_gap_pct"] < a["weighted_gap_pct"]  # B ahead on recent form
    assert (a["rank_flat"], b["rank_flat"]) == (1, 2)
    assert (a["rank_weighted"], b["rank_weighted"]) == (2, 1)
    assert b["form_places"] == 1 and a["form_places"] == -1


def test_form_is_none_below_the_minimum_rounds():
    rounds = _season({r: [("A", 2.4, 4.4), ("B", 2.5, 4.8)] for r in range(1, MIN_ROUNDS_FOR_FORM)})
    assert all(r["form_places"] is None for r in build_view(rounds, IDENT, {}, MIN_ROUNDS_FOR_FORM))


def test_rows_are_sorted_best_weighted_gap_first_and_labels_carry_the_colour_team():
    rounds = _season({1: [("A", 2.4, 4.4), ("B", 2.5, 4.8)]})
    rows = build_view(rounds, {"A": "Pu1", "B": "Pu2"}.get, {"Pu1": ("Pu1", "Works1"), "Pu2": ("Pu2", "Works2")}, 1)
    assert [r["key"] for r in rows] == ["Pu1", "Pu2"]
    assert rows[0]["color_team"] == "Works1"


# ---- DB orchestrator ------------------------------------------------------------------------


def _seed(db: Session, year: int, rounds: dict[int, list[tuple]]):
    for rnd, cars in rounds.items():
        wk = RaceWeekend(year=year, round=rnd, circuit_name="X", country="Y", event_name=f"GP {rnd}")
        db.add(wk)
        db.commit()
        db.refresh(wk)
        race = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
        sprint = SessionRow(weekend_id=wk.id, session_type="SPRINT", status="loaded")
        db.add(race)
        db.add(sprint)
        db.commit()
        db.refresh(race)
        db.refresh(sprint)
        for team, a, b in cars:
            db.add(RaceStart(session_id=race.id, driver=f"{team}1", constructor=team, t_0_100_s=a, t_0_200_s=b))
        # A sprint start must never leak into the season view.
        db.add(RaceStart(session_id=sprint.id, driver="SPR", constructor="Ferrari", t_0_100_s=1.0, t_0_200_s=2.0))
        db.commit()


def test_build_season_start_end_to_end_with_a_fallback_round_and_a_no_data_round(db_session):
    _seed(
        db_session,
        2026,
        {
            1: [("Ferrari", 2.4, 4.4), ("McLaren", 2.5, 4.84)],
            2: [("Ferrari", 2.4, None), ("McLaren", 2.6, None)],  # 0-100 only
        },
    )
    wk = RaceWeekend(year=2026, round=3, circuit_name="X", country="Y", event_name="GP 3")  # no race rows
    db_session.add(wk)
    db_session.commit()
    out = build_season_start(2026, db_session)
    assert [r["round"] for r in out["rounds"]] == [1, 2, 3]  # every weekend, like Gap by round
    teams = {r["key"]: r for r in out["views"]["teams"]["rows"]}
    assert [p["round"] for p in teams["McLaren"]["points"]] == [1, 2]  # nothing invented for round 3
    assert teams["Ferrari"]["points"][0]["gap_pct"] == pytest.approx(0.0)
    assert set(out["views"]) == {"teams", "pu"}  # 2026 and both teams are in the supply map
    pu = {r["key"]: r for r in out["views"]["pu"]["rows"]}
    assert set(pu) == {"Ferrari", "Mercedes"}  # McLaren runs Mercedes power


def test_other_seasons_and_unmapped_teams_get_no_power_unit_view(db_session):
    _seed(db_session, 2051, {1: [("Ferrari", 2.4, 4.4), ("McLaren", 2.5, 4.84)]})
    assert "pu" not in build_season_start(2051, db_session)["views"]  # supply map is 2026-only
    _seed(db_session, 2026, {1: [("Ferrari", 2.4, 4.4), ("Brand New Team", 2.5, 4.84)]})
    assert "pu" not in build_season_start(2026, db_session)["views"]  # not every team is mapped


def test_empty_season_has_empty_views(db_session):
    assert build_season_start(2049, db_session) == {"rounds": [], "views": {}}


def test_pu_map_applies_only_to_its_season_and_only_when_it_covers_every_team():
    assert pu_map_applies(2026, {"Ferrari", "McLaren", "Audi"})
    assert not pu_map_applies(2025, {"Ferrari", "McLaren"})  # Red Bull ran Honda in 2025
    assert not pu_map_applies(2026, {"Ferrari", "Brand New Team"})
