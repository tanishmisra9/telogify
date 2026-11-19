import pandas as pd
from sqlmodel import select

from telogify.ingest.results import (
    classified_gap,
    compound_letter,
    compute_gap,
    extract_results,
    finishing_intervals,
    lap_clock,
    lapped_gap,
    format_gap_label,
    format_total_time,
    is_lapped,
    laps_down,
    points_for_session,
    race_points,
    race_results_complete,
    requires_complete_results,
    sprint_points,
    strategy_string,
)


class _FakeSession:
    def __init__(self, name: str, results: pd.DataFrame):
        self.name = name
        self.results = results


def test_extract_results_captures_quali_segment_times():
    results = pd.DataFrame(
        [
            {
                "Position": 1,
                "Abbreviation": "VER",
                "TeamName": "Red Bull Racing",
                "Time": pd.NaT,
                "Laps": pd.NA,
                "Status": "",
                "Q1": pd.Timedelta(seconds=90.123),
                "Q2": pd.Timedelta(seconds=89.456),
                "Q3": pd.Timedelta(seconds=88.789),
            },
            {
                "Position": 16,
                "Abbreviation": "STR",
                "TeamName": "Aston Martin",
                "Time": pd.NaT,
                "Laps": pd.NA,
                "Status": "",
                "Q1": pd.Timedelta(seconds=91.5),
                "Q2": pd.NaT,
                "Q3": pd.NaT,
            },
        ]
    )
    rows = extract_results(_FakeSession("Qualifying", results))
    ver = next(r for r in rows if r.driver == "VER")
    stroll = next(r for r in rows if r.driver == "STR")
    assert ver.q1_time_s == 90.123
    assert ver.q2_time_s == 89.456
    assert ver.q3_time_s == 88.789
    assert stroll.q1_time_s == 91.5
    assert stroll.q2_time_s is None
    assert stroll.q3_time_s is None


def test_extract_results_no_quali_segments_for_race_session():
    results = pd.DataFrame(
        [
            {
                "Position": 1,
                "Abbreviation": "VER",
                "TeamName": "Red Bull Racing",
                "Time": pd.Timedelta(seconds=5400),
                "Laps": 58.0,
                "Status": "Finished",
            }
        ]
    )
    rows = extract_results(_FakeSession("Race", results))
    assert rows[0].q1_time_s is None
    assert rows[0].q2_time_s is None
    assert rows[0].q3_time_s is None


def _race_row(abbr, position, grid="absent", **extra):
    row = {"Position": position, "Abbreviation": abbr, "TeamName": "T", "Time": pd.NaT, "Laps": 50.0, "Status": "Finished", **extra}
    if grid != "absent":
        row["GridPosition"] = grid
    return row


def test_extract_results_reads_the_official_grid_for_race_and_sprint_only():
    race = pd.DataFrame([_race_row("VER", 1, 20.0), _race_row("NOR", 2, 3.0)])
    for name in ("Race", "Sprint"):
        grids = {r.driver: r.grid for r in extract_results(_FakeSession(name, race))}
        assert grids == {"VER": 20, "NOR": 3}  # VER set no quali time and started P20: the point of the field
    # Qualifying ignores the column even when present (its "grid" is the classification itself)
    assert {r.grid for r in extract_results(_FakeSession("Qualifying", race))} == {None}


def test_extract_results_grid_zero_is_a_pit_lane_start_and_junk_is_none():
    race = pd.DataFrame([_race_row("AAA", 1, float("nan")), _race_row("BBB", 2, 0.0), _race_row("CCC", 3, -1.0), _race_row("DDD", 4)])
    # 0 is KEPT (pit lane, not a slot); NaN, negative and a missing column are None
    assert [r.grid for r in extract_results(_FakeSession("Race", race))] == [None, 0, None, None]


def test_store_results_persists_the_official_grid(db_session):
    from telogify.ingest.loader import WeekendData
    from telogify.ingest.results import store_results
    from telogify.models import RaceWeekend, Session as SessionRow, SessionResult

    wk = RaceWeekend(year=2067, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    race = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
    db_session.add(race)
    db_session.commit()
    db_session.refresh(race)
    frame = pd.DataFrame([_race_row("VER", 1, 20.0), _race_row("NOR", 2, float("nan"))])
    store_results(WeekendData(weekend=wk, sessions={"R": _FakeSession("Race", frame)}), db_session)
    stored = {r.driver: r.grid for r in db_session.exec(select(SessionResult).where(SessionResult.session_id == race.id)).all()}
    assert stored == {"VER": 20, "NOR": None}


def test_race_points_by_position():
    assert race_points(1) == 25
    assert race_points(10) == 1
    assert race_points(11) == 0
    assert race_points(None) == 0


def test_sprint_points_by_position():
    assert sprint_points(1) == 8
    assert sprint_points(8) == 1
    assert sprint_points(9) == 0
    assert sprint_points(None) == 0


def test_points_for_session():
    assert points_for_session("R", 1) == 25
    assert points_for_session("SPRINT", 1) == 8
    assert points_for_session("Q", 1) == 25


def test_compound_letter():
    assert compound_letter("SOFT") == "S"
    assert compound_letter("intermediate") == "I"
    assert compound_letter(None) == "?"
    assert compound_letter("Experimental") == "E"  # unknown -> first letter


def test_strategy_string():
    assert strategy_string(["MEDIUM", "HARD", "MEDIUM"]) == "M-H-M"
    assert strategy_string(["SOFT", "MEDIUM"]) == "S-M"
    # A stint with no tyre data (missing, or FastF1's literal "None"/"UNKNOWN") is left out.
    assert strategy_string(["SOFT", "None", "MEDIUM"]) == "S-M"
    assert strategy_string([None]) == ""
    assert strategy_string(["UNKNOWN"]) == ""
    assert strategy_string([]) == ""


def test_format_total_time():
    assert format_total_time(5432.106) == "1:30:32.106"
    assert format_total_time(92.5) == "1:32.500"  # hours dropped when zero
    assert format_total_time(None) is None


def test_leader_gap_is_zero_in_race():
    assert compute_gap(1, 5400.0, is_race=True) == 0.0


def test_follower_gap_is_time_in_race():
    assert compute_gap(2, 12.3, is_race=True) == 12.3


def test_non_race_has_no_gap():
    assert compute_gap(1, 80.0, is_race=False) is None


def test_missing_time_has_no_gap():
    assert compute_gap(5, None, is_race=True) is None


def test_lapped_driver_has_no_time_gap():
    assert (
        compute_gap(
            9,
            15.334,
            is_race=True,
            status="Lapped",
            laps=70.0,
            leader_laps=71.0,
        )
        is None
    )


def test_is_lapped_by_status_or_lap_count():
    assert is_lapped("Lapped", 70.0, 71.0)
    assert is_lapped("Finished", 69.0, 71.0)
    assert not is_lapped("Finished", 71.0, 71.0)


def test_laps_down():
    assert laps_down(70.0, 71.0) == 1
    assert laps_down(68.0, 71.0) == 3
    assert laps_down(71.0, 71.0) is None


def test_format_gap_label_multi_lap():
    leader = 71.0
    assert format_gap_label(1, 0.0, 71.0, leader, "Finished") == "leader"
    assert format_gap_label(2, 1.6, 71.0, leader, "Finished") == "+1.6s"
    assert format_gap_label(9, None, 70.0, leader, "Lapped") == "+1 Lap"
    assert format_gap_label(16, None, 69.0, leader, "Lapped") == "+2 Laps"
    assert format_gap_label(18, None, 68.0, leader, "Lapped") == "+3 Laps"
    assert format_gap_label(19, None, 45.0, leader, "Retired") == "DNF"


def test_format_gap_label_shows_tenth_second_gap():
    assert format_gap_label(2, 0.312, None, None, "Finished") == "+0.3s"


def test_format_gap_label_dns():
    assert format_gap_label(20, None, None, None, "Did not start") == "DNS"


def test_laps_down_none_when_lap_counts_missing():
    assert laps_down(None, 71.0) is None
    assert laps_down(70.0, None) is None


def test_format_gap_label_lapped_without_lap_counts_falls_back():
    assert format_gap_label(9, None, None, None, "Lapped") == "+1 Lap"


def test_format_gap_label_unmapped_status_returned_verbatim():
    assert format_gap_label(15, None, None, None, "Disqualified") == "Disqualified"


def test_int_and_float_helpers_handle_unparseable_values():
    from telogify.ingest.results import _float, _int

    assert _int("not-a-number") is None
    assert _int(float("nan")) is None
    assert _float(float("nan")) is None
    assert _float("not-a-number") is None


# --- store_results: DB orchestration ----------------------------------------


def test_store_results_persists_rows_and_skips_unmatched_session(db_session):
    from telogify.ingest.loader import WeekendData
    from telogify.ingest.results import store_results
    from telogify.models import RaceWeekend, Session as SessionRow, SessionResult

    wk = RaceWeekend(year=2066, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    race = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
    db_session.add(race)
    db_session.commit()
    db_session.refresh(race)

    results = pd.DataFrame(
        [
            {"Position": 1, "Abbreviation": "VER", "TeamName": "Red Bull Racing", "Time": pd.Timedelta(seconds=5400), "Laps": 58.0, "Status": "Finished"},
        ]
    )
    race_session = _FakeSession("Race", results)
    data = WeekendData(weekend=wk, sessions={"R": race_session, "Q": race_session})  # "Q" has no matching DB row

    store_results(data, db_session)

    stored = db_session.exec(select(SessionResult).where(SessionResult.session_id == race.id)).all()
    assert len(stored) == 1
    assert stored[0].driver == "VER"

    # idempotent re-run (delete + reinsert) leaves exactly one row
    store_results(data, db_session)
    stored_again = db_session.exec(select(SessionResult).where(SessionResult.session_id == race.id)).all()
    assert len(stored_again) == 1


def _race_frame(*, winner_time, statuses, positions=None):
    n = len(statuses)
    return pd.DataFrame(
        {
            "Position": positions if positions is not None else [float(i + 1) for i in range(n)],
            "Time": [winner_time] + [pd.Timedelta(seconds=5 * i) for i in range(1, n)],
            "Status": statuses,
        }
    )


def test_race_results_complete_accepts_a_full_table():
    res = _race_frame(
        winner_time=pd.Timedelta(hours=1, minutes=42), statuses=["Finished", "Finished", "Lapped", "Retired"]
    )
    assert race_results_complete(res) is True


def test_race_results_complete_rejects_the_degraded_table_stored_on_prod():
    # Position-only fallback: no winner Time, no Status at all (NaN and None both occur).
    res = _race_frame(winner_time=pd.NaT, statuses=[None, float("nan"), "", None])
    assert race_results_complete(res) is False


def test_race_results_complete_needs_both_winner_time_and_status():
    statuses = ["Finished"] * 4
    assert race_results_complete(_race_frame(winner_time=pd.NaT, statuses=statuses)) is False
    res = _race_frame(winner_time=pd.Timedelta(hours=1), statuses=[None] * 4)
    assert race_results_complete(res) is False


def test_race_results_complete_tolerates_a_few_blank_statuses_but_not_most():
    t = pd.Timedelta(hours=1)
    assert race_results_complete(_race_frame(winner_time=t, statuses=["Finished", "Finished", "Lapped", ""])) is True
    assert race_results_complete(_race_frame(winner_time=t, statuses=["Finished", "", "", ""])) is False


def test_race_results_complete_rejects_missing_winner_row_empty_and_none():
    t = pd.Timedelta(hours=1)
    no_p1 = _race_frame(winner_time=t, statuses=["Finished"] * 3, positions=[2.0, 3.0, float("nan")])
    assert race_results_complete(no_p1) is False
    assert race_results_complete(pd.DataFrame()) is False
    assert race_results_complete(None) is False
    assert race_results_complete(pd.DataFrame({"Position": [1.0]})) is False  # columns absent


def test_requires_complete_results_is_race_like_only():
    assert requires_complete_results("Race") and requires_complete_results("Sprint")
    for name in ("Practice 1", "Qualifying", "Sprint Qualifying", "Sprint Shootout"):
        assert not requires_complete_results(name)


# --- numeric gaps for the Finishing order switcher ---------------------------------------

def test_classified_gap_only_for_lead_lap_finishers():
    assert classified_gap(1, 0.0, 57, 57, "Finished") == 0.0
    assert classified_gap(2, 4.2, 57, 57, "Finished") == 4.2
    assert classified_gap(5, None, 57, 57, "") is None  # a degraded round: no time
    assert classified_gap(9, 12.0, 56, 57, "Finished") is None  # a lap down: a stored gap is not trusted
    assert classified_gap(12, 30.0, 57, 57, "Lapped") is None
    assert classified_gap(19, 55.0, 20, 57, "Retired") is None  # forbidden: a retired car never gets seconds
    assert classified_gap(21, 0.0, 0, 57, "Did not start") is None
    assert classified_gap(8, 40.0, 57, 57, "Disqualified") is None  # finished all laps, but not classified
    assert classified_gap(8, 40.0, 57, 57, "Withdrew") is None  # any status outside the allow-list


def test_finishing_intervals_gap_to_the_car_ahead():
    assert finishing_intervals([0.0, 2.5, 4.0, 10.0]) == [None, 2.5, 1.5, 6.0]


def test_finishing_intervals_never_bridge_a_lapped_or_missing_car():
    # P3 is a lap down: P4 (also lap down), and P3 itself, have no interval; P2 still does.
    assert finishing_intervals([0.0, 2.5, None, None]) == [None, 2.5, None, None]
    # A gap behind a missing one is unknowable: it must NOT fall back to the gap to the leader.
    assert finishing_intervals([0.0, None, 9.0]) == [None, None, None]


def test_finishing_intervals_never_negative():
    # P4 at +20 s, P5 at +19 s (a penalty-adjusted or stale time): no gap, not -1.
    assert finishing_intervals([0.0, 10.0, 20.0, 19.0, 25.0]) == [None, 10.0, 10.0, None, 6.0]


def test_finishing_intervals_empty_and_single():
    assert finishing_intervals([]) == []
    assert finishing_intervals([0.0]) == [None]


class _LapSession(_FakeSession):
    def __init__(self, name, results, laps):
        super().__init__(name, results)
        self.laps = laps


def _laps(driver, ends):
    """One lap row per (lap number, session clock at the end of that lap)."""
    return [{"Driver": driver, "LapNumber": float(n), "Time": pd.Timedelta(seconds=t)} for n, t in ends]


def test_lapped_gap_is_the_gap_to_the_leader_at_the_cars_last_lap_not_its_delay_at_the_flag():
    # WIN does 3 laps (100 s each).
    # LAP is a lap down: it ends lap 1 at 110 and lap 2 at 305, i.e. it crossed the line 5 s after the winner.
    results = pd.DataFrame(
        [
            _race_row("WIN", 1, 1.0, Time=pd.Timedelta(seconds=300), Laps=3.0),
            _race_row("AHD", 2, 2.0, Time=pd.Timedelta(seconds=3.0), Laps=3.0),
            _race_row("LAP", 3, 3.0, Time=pd.Timedelta(seconds=5.0), Laps=2.0, Status="Lapped"),
            _race_row("RET", 4, 4.0, Time=pd.Timedelta(seconds=40.0), Laps=1.0, Status="Retired"),
        ]
    )
    laps = pd.DataFrame(
        _laps("WIN", [(1, 100), (2, 200), (3, 300)]) + _laps("AHD", [(1, 101), (2, 201), (3, 303)])
        + _laps("LAP", [(1, 110), (2, 305)]) + _laps("RET", [(1, 140)])
    )
    rows = {r.driver: r for r in extract_results(_LapSession("Race", results, laps))}
    # LAP: its clock after lap 2 (305) minus the leader's after lap 2 (200) = 105, NOT the 5 s it crossed the line after the winner
    assert rows["LAP"].lapped_gap_s == 105.0
    assert rows["LAP"].gap_to_leader is None  # agent tools read gap_to_leader: a lapped car must never look like a lead-lap gap
    assert [rows[d].lapped_gap_s for d in ("WIN", "AHD", "RET")] == [None, None, None]
    assert rows["AHD"].gap_to_leader == 3.0  # lead-lap behaviour unchanged


def test_lapped_gap_is_none_rather_than_guessed_when_a_lap_is_missing_or_not_a_race():
    clock = lap_clock(_LapSession("Race", pd.DataFrame(), pd.DataFrame(_laps("WIN", [(1, 100), (2, 200)]) + _laps("LAP", [(1, 110)]))))
    assert clock == {("WIN", 1): 100.0, ("WIN", 2): 200.0, ("LAP", 1): 110.0}
    assert lapped_gap(clock, "LAP", "WIN", 1.0, True, status="Lapped") == 10.0
    assert lapped_gap(clock, "LAP", "WIN", 2.0, True, status="Lapped") is None  # the car's lap 2 is not in the table
    assert lapped_gap(clock, "LAP", "WIN", 1.0, False, status="Lapped") is None  # not a race
    assert lapped_gap(clock, "LAP", "WIN", 1.0, True, status="Retired") is None
    assert lapped_gap(clock, "LAP", None, 1.0, True, status="Lapped") is None  # no leader
    assert lapped_gap({("WIN", 1): 100.0, ("LAP", 1): 90.0}, "LAP", "WIN", 1.0, True, status="Lapped") is None  # negative is junk
    # a session with no lap table (FakeSession) simply has no clock
    assert lap_clock(_FakeSession("Race", pd.DataFrame())) == {}


def test_lap_clock_is_empty_for_a_results_only_load_that_raises_on_laps():
    from fastf1.exceptions import DataNotLoadedError

    class _ResultsOnly(_FakeSession):
        @property
        def laps(self):
            raise DataNotLoadedError("laps not loaded")

    assert lap_clock(_ResultsOnly("Race", pd.DataFrame())) == {}


def test_store_results_persists_the_lapped_gap(db_session):
    from telogify.ingest.loader import WeekendData
    from telogify.ingest.results import store_results
    from telogify.models import RaceWeekend, Session as SessionRow, SessionResult

    wk = RaceWeekend(year=2068, round=1, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)
    race = SessionRow(weekend_id=wk.id, session_type="R", status="loaded")
    db_session.add(race)
    db_session.commit()
    db_session.refresh(race)
    frame = pd.DataFrame(
        [_race_row("WIN", 1, 1.0, Time=pd.Timedelta(seconds=200), Laps=2.0), _race_row("LAP", 2, 2.0, Time=pd.Timedelta(seconds=7.5), Laps=1.0, Status="Lapped")]
    )
    laps = pd.DataFrame(_laps("WIN", [(1, 100), (2, 200)]) + _laps("LAP", [(1, 207.5)]))  # crosses 7.5 s after the winner, a lap down
    store_results(WeekendData(weekend=wk, sessions={"R": _LapSession("Race", frame, laps)}), db_session)
    stored = {r.driver: r.lapped_gap_s for r in db_session.exec(select(SessionResult).where(SessionResult.session_id == race.id)).all()}
    assert stored == {"WIN": None, "LAP": 107.5}


def test_lapped_gap_is_not_published_when_the_lap_table_disagrees_with_the_results_delay():
    clock = {("WIN", 2): 200.0, ("WIN", 3): 300.0, ("LAP", 2): 305.0}
    # results say the car crossed 5 s after the winner and the table agrees (305 - 300): published
    assert lapped_gap(clock, "LAP", "WIN", 2.0, True, status="Lapped", leader_laps=3.0, flag_delay_s=5.0) == 105.0
    # results say 60 s but the table says 5 s: a truncated or renumbered table, so no figure rather than a plausible wrong one
    assert lapped_gap(clock, "LAP", "WIN", 2.0, True, status="Lapped", leader_laps=3.0, flag_delay_s=60.0) is None
    # a 10 s post-race time penalty makes the official delay 10 s longer than the clock's: still published (the on-track clock)
    assert lapped_gap(clock, "LAP", "WIN", 2.0, True, status="Lapped", leader_laps=3.0, flag_delay_s=15.0) == 105.0
    # official LESS than the clock says is impossible with a penalty: the table is wrong
    assert lapped_gap(clock, "LAP", "WIN", 2.0, True, status="Lapped", leader_laps=3.0, flag_delay_s=3.0) is None
    # the leader's final lap is not in the table: cannot verify, so None
    assert lapped_gap({("WIN", 2): 200.0, ("LAP", 2): 305.0}, "LAP", "WIN", 2.0, True, status="Lapped", leader_laps=3.0, flag_delay_s=5.0) is None
    # no upstream delay at all (3 of 141 in 2026): nothing to cross-check against, the table alone is used
    assert lapped_gap(clock, "LAP", "WIN", 2.0, True, status="Lapped", leader_laps=3.0, flag_delay_s=None) == 105.0
