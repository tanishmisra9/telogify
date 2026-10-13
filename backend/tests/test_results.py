import pandas as pd
from sqlmodel import select

from telogify.ingest.results import (
    compound_letter,
    compute_gap,
    extract_results,
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
