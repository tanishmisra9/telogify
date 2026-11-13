"""DB extractors (`extract_*` / `store_*`) run end to end against a fake FastF1 session.

The pure helpers in each ingest module have their own tests; this file covers the glue that
reads a session and writes rows, including the CLAUDE.md invariant that every ingest extractor
is idempotent per session (delete + reinsert). See `fastf1_fakes.py` for the fixture.
"""

import types

import pandas as pd
import pytest
from fastf1_fakes import fake_session, lap_row, lap_telemetry, patch_telemetry
from sqlmodel import select

from telogify.ingest import segment
from telogify.ingest.accel_samples import extract_accel_samples, store_accel_samples
from telogify.ingest.deployment import extract_deployment, store_deployment
from telogify.ingest.loader import WeekendData
from telogify.ingest.quali_character import extract_quali_character, store_quali_character
from telogify.ingest.quali_trace import extract_quali_traces, store_quali_traces
from telogify.ingest.sectors import extract_sector_bests, store_sector_bests
from telogify.ingest.stints import extract_stints, fuel_effect_for_race, store_stints
from telogify.ingest.straights import extract_straights, store_straights
from telogify.models import (
    AccelSample,
    DeploymentTrace,
    QualiCharacter,
    QualiTrace,
    RaceWeekend,
    SectorBest,
    Session,
    Stint,
    StraightSegment,
)

CORNERS = [(1, 600.0, ""), (2, 1500.0, ""), (3, 2400.0, "")]


def _rows(drivers=(("AAA", "Alpha", 90.0), ("BBB", "Beta", 91.0)), laps=3):
    rows = []
    for driver, team, base in drivers:
        for n in range(1, laps + 1):
            rows.append(
                lap_row(driver, n, base, team=team, position=1 if driver == drivers[0][0] else 2,
                        sectors=(30.0, 30.0, base - 60.0), stint=1 if n <= 2 else 2)
            )
    return rows


def _results(pole: str) -> pd.DataFrame:
    drivers = ["AAA", "BBB", "CCC"]
    others = iter([2.0, 3.0])
    return pd.DataFrame(
        {"Abbreviation": drivers, "Position": [1.0 if d == pole else next(others) for d in drivers]}
    )


def _seed(db, codes, session, round=1):
    weekend = RaceWeekend(year=2026, round=round, circuit_name="C", country="X", event_name=f"E{round}")
    db.add(weekend)
    db.commit()
    db.refresh(weekend)
    ids = {}
    for code in codes:
        row = Session(weekend_id=weekend.id, session_type=code)
        db.add(row)
        db.commit()
        db.refresh(row)
        ids[code] = row.id
    return WeekendData(weekend=weekend, sessions={c: session for c in codes}), ids


def _count(db, model, session_id):
    return len(db.exec(select(model).where(model.session_id == session_id)).all())


# --- idempotency: first store writes rows, second store replaces them exactly -----------------

STORES = [
    ("straights", store_straights, StraightSegment, "Q", dict(drs_zone_id=99)),
    ("quali_character", store_quali_character, QualiCharacter, "Q", {}),
    ("deployment", store_deployment, DeploymentTrace, "Q", {}),
    ("quali_trace", store_quali_traces, QualiTrace, "Q", {}),
    ("accel", store_accel_samples, AccelSample, "R", {}),
    ("sectors", store_sector_bests, SectorBest, "Q", dict(sector=9, best_time_s=1.0)),
    ("stints", store_stints, Stint, "R", dict(stint_number=99)),
]


@pytest.mark.parametrize("name,store,model,code,stale_extra", STORES, ids=[s[0] for s in STORES])
def test_store_is_idempotent_and_replaces_stale_rows(db_session, monkeypatch, name, store, model, code, stale_extra):
    patch_telemetry(monkeypatch, {"AAA": lap_telemetry(), "BBB": lap_telemetry(1.01)})
    data, ids = _seed(db_session, [code], fake_session(_rows(), corners=CORNERS, results=_results("AAA")))
    sid = ids[code]

    store(data, db_session)
    first = _count(db_session, model, sid)
    assert first > 0, "fixture must produce rows, or the idempotency check below is vacuous"

    db_session.add(model(session_id=sid, driver="ZZZ", **stale_extra))
    db_session.commit()
    assert _count(db_session, model, sid) == first + 1

    store(data, db_session)
    rows = db_session.exec(select(model).where(model.session_id == sid)).all()
    assert len(rows) == first
    assert all(r.driver != "ZZZ" for r in rows)


@pytest.mark.parametrize(
    "store,model,wrong_code",
    [
        (store_deployment, DeploymentTrace, "R"),
        (store_quali_traces, QualiTrace, "R"),
        (store_quali_character, QualiCharacter, "R"),
        (store_accel_samples, AccelSample, "Q"),
    ],
)
def test_gated_stores_ignore_other_session_types(db_session, monkeypatch, store, model, wrong_code):
    patch_telemetry(monkeypatch, {"AAA": lap_telemetry(), "BBB": lap_telemetry(1.01)})
    data, ids = _seed(db_session, [wrong_code], fake_session(_rows(), corners=CORNERS))
    store(data, db_session)
    assert _count(db_session, model, ids[wrong_code]) == 0


@pytest.mark.parametrize(
    "store,model",
    [(store_straights, StraightSegment), (store_sector_bests, SectorBest), (store_stints, Stint),
     (store_deployment, DeploymentTrace), (store_quali_traces, QualiTrace),
     (store_quali_character, QualiCharacter), (store_accel_samples, AccelSample)],
)
def test_store_skips_a_session_with_no_db_row(db_session, monkeypatch, store, model):
    """A loaded FastF1 session whose `session` row was never created is skipped, not a crash."""
    patch_telemetry(monkeypatch, {"AAA": lap_telemetry(), "BBB": lap_telemetry()})
    weekend = RaceWeekend(year=2026, round=2, circuit_name="C", country="X", event_name="E")
    db_session.add(weekend)
    db_session.commit()
    db_session.refresh(weekend)
    data = WeekendData(weekend=weekend, sessions={"Q": fake_session(_rows()), "R": fake_session(_rows())})
    store(data, db_session)  # no exception, nothing written
    assert db_session.exec(select(Session)).all() == []
    assert db_session.exec(select(model)).all() == []  # nothing written under a guessed session_id


# --- straights -----------------------------------------------------------------------------------

def test_extract_straights_reports_max_and_trap_per_zone(monkeypatch):
    patch_telemetry(monkeypatch, {"AAA": lap_telemetry(), "BBB": lap_telemetry(1.01)})
    out = extract_straights(fake_session(_rows(), corners=CORNERS))
    assert set(out) == {"AAA", "BBB"}
    assert out["AAA"], "at least one zone has samples"
    assert all(s.max_speed_kmh >= s.trap_speed_kmh for s in out["AAA"])


def test_extract_straights_skips_a_driver_whose_telemetry_will_not_merge(monkeypatch):
    patch_telemetry(monkeypatch, {"AAA": None, "BBB": lap_telemetry()})
    assert set(extract_straights(fake_session(_rows(), corners=CORNERS))) == {"BBB"}


def test_extract_straights_needs_a_session_with_laps_and_two_corners(monkeypatch):
    patch_telemetry(monkeypatch, {"AAA": lap_telemetry(), "BBB": lap_telemetry()})
    assert extract_straights(fake_session([])) == {}
    assert extract_straights(fake_session(_rows(), corners=[(1, 600.0, "")])) == {}
    assert extract_straights(fake_session(_rows())) == {}


# --- sectors -------------------------------------------------------------------------------------

def test_extract_sector_bests_takes_the_minimum_and_ignores_deleted_laps():
    rows = [
        lap_row("AAA", 1, 90.0, sectors=(30.0, 30.0, 30.0)),
        lap_row("AAA", 2, 89.0, sectors=(25.0, 31.0, 33.0), deleted=True),  # illegally fast
        lap_row("AAA", 3, 90.0, sectors=(29.0, None, 31.0)),
    ]
    got = {(b.driver, b.sector): b.best_time_s for b in extract_sector_bests(fake_session(rows))}
    assert got == {("AAA", 1): 29.0, ("AAA", 2): 30.0, ("AAA", 3): 30.0}


def test_extract_sector_bests_empty_session():
    assert extract_sector_bests(fake_session([])) == []


# --- quali character ------------------------------------------------------------------------------

def test_extract_quali_character_reads_top_speed_and_corner_minima(monkeypatch):
    patch_telemetry(monkeypatch, {"AAA": lap_telemetry(), "BBB": None})
    out = extract_quali_character(fake_session(_rows(), corners=CORNERS))
    assert set(out) == {"AAA"}  # BBB's telemetry failed and is skipped
    constructor, lap_time_s, char = out["AAA"]
    assert (constructor, lap_time_s) == ("Alpha", 90.0)
    assert char.top_speed_kmh == pytest.approx(320.0)
    assert 0 < char.full_throttle_pct < 1


def test_extract_quali_character_empty_session():
    assert extract_quali_character(fake_session([])) == {}


# --- deployment -----------------------------------------------------------------------------------

def test_extract_deployment_flags_the_clipping_car_and_not_the_clean_one(monkeypatch):
    patch_telemetry(monkeypatch, {"AAA": lap_telemetry(), "BBB": lap_telemetry(clip=False)})
    out = extract_deployment(fake_session(_rows()))
    assert out["AAA"]["constructor"] == "Alpha"
    assert out["AAA"]["summary"]["n_clips"] == 2
    assert [s["is_clip"] for s in out["AAA"]["straights"]] == [True, True]
    # Same straights, but speed holds at full throttle: found as straights, none is a clip.
    assert out["BBB"]["summary"]["n_straights"] == 2
    assert out["BBB"]["summary"]["n_clips"] == 0
    assert [s["is_clip"] for s in out["BBB"]["straights"]] == [False, False]


def test_extract_deployment_skips_unmergeable_telemetry_and_empty_sessions(monkeypatch):
    patch_telemetry(monkeypatch, {"AAA": None, "BBB": None})
    assert extract_deployment(fake_session(_rows())) == {}
    assert extract_deployment(fake_session([])) == {}


# --- accel samples --------------------------------------------------------------------------------

def test_extract_accel_samples_collects_full_throttle_points(monkeypatch):
    patch_telemetry(monkeypatch, {"AAA": lap_telemetry(), "BBB": None})
    out = extract_accel_samples(fake_session(_rows()))
    assert set(out) == {"AAA"}
    assert out["AAA"]["constructor"] == "Alpha"
    assert len(out["AAA"]["points"]) > 0
    assert all(p[0] > 0 for p in out["AAA"]["points"])


def test_extract_accel_samples_drops_telemetry_without_position_columns(monkeypatch):
    tel = lap_telemetry().drop(columns=["X", "Y"])
    patch_telemetry(monkeypatch, {"AAA": tel, "BBB": tel})
    assert extract_accel_samples(fake_session(_rows())) == {}
    assert extract_accel_samples(fake_session([])) == {}


# --- quali trace ----------------------------------------------------------------------------------

def _trace_rows():
    return _rows(drivers=(("AAA", "Alpha", 90.0), ("BBB", "Beta", 91.0), ("CCC", "Gamma", 92.0)))


def test_extract_quali_traces_marks_the_official_pole_not_the_fastest(monkeypatch):
    patch_telemetry(monkeypatch, {d: lap_telemetry(s) for d, s in (("AAA", 1.0), ("BBB", 1.01), ("CCC", 1.02))})
    traces, grid = extract_quali_traces(fake_session(_trace_rows(), results=_results("BBB")))
    assert {d for d, v in traces.items() if v["is_pole"]} == {"BBB"}
    assert len(grid) > 2
    assert all(len(v["delta_s"]) == len(grid) for v in traces.values())
    assert traces["BBB"]["delta_s"] == [0.0] * len(grid)  # the pole row is its own reference


def test_extract_quali_traces_marks_no_pole_when_the_pole_lap_is_scrubbed(monkeypatch):
    """2026 R3 Japan: the pole sitter's recorded distance is implausible, so they are excluded
    and the runner-up must NOT be promoted to pole."""
    patch_telemetry(
        monkeypatch,
        {"AAA": lap_telemetry(0.5), "BBB": lap_telemetry(1.01), "CCC": lap_telemetry(1.0)},
    )
    traces, _ = extract_quali_traces(fake_session(_trace_rows(), results=_results("AAA")))
    assert "AAA" not in traces
    assert traces and not any(v["is_pole"] for v in traces.values())


def test_extract_quali_traces_without_official_results_has_no_pole(monkeypatch):
    patch_telemetry(monkeypatch, {"AAA": lap_telemetry(), "BBB": lap_telemetry(1.01), "CCC": lap_telemetry()})
    traces, _ = extract_quali_traces(fake_session(_trace_rows(), results=pd.DataFrame()))
    assert traces and not any(v["is_pole"] for v in traces.values())


def test_extract_quali_traces_ignores_results_rows_without_a_position(monkeypatch):
    patch_telemetry(monkeypatch, {"AAA": lap_telemetry(), "BBB": lap_telemetry(1.01), "CCC": lap_telemetry()})
    results = pd.DataFrame({"Abbreviation": ["AAA", "BBB"], "Position": [float("nan"), 2.0]})
    traces, _ = extract_quali_traces(fake_session(_trace_rows(), results=results))
    assert not any(v["is_pole"] for v in traces.values())


def test_extract_quali_traces_empty_when_nothing_usable(monkeypatch):
    assert extract_quali_traces(fake_session([])) == ({}, [])
    patch_telemetry(monkeypatch, {"AAA": None, "BBB": None, "CCC": None})
    assert extract_quali_traces(fake_session(_trace_rows())) == ({}, [])


def test_store_quali_traces_records_corners_and_grid(db_session, monkeypatch):
    patch_telemetry(monkeypatch, {"AAA": lap_telemetry(), "BBB": lap_telemetry(1.01)})
    data, ids = _seed(db_session, ["Q"], fake_session(_rows(), corners=CORNERS, results=_results("AAA")))
    store_quali_traces(data, db_session)
    row = db_session.exec(select(QualiTrace).where(QualiTrace.driver == "AAA")).one()
    assert row.is_pole and [c["number"] for c in row.corners_json] == [1, 2, 3]
    assert len(row.grid_m) == len(row.speed_kmh)


# --- stints ---------------------------------------------------------------------------------------

def _race_rows():
    rows = []
    for n in range(1, 5):
        rows.append(lap_row("AAA", n, 90.0, position=1, stint=1 if n <= 2 else 2, compound="SOFT" if n <= 2 else "HARD"))
        rows.append(lap_row("BBB", n, 90.0, position=2, start_s=(n - 1) * 100.0 + 1.5, stint=1))
    return rows


def test_extract_stints_splits_stints_and_computes_gap_to_car_ahead():
    out = extract_stints(fake_session(_race_rows()))
    assert [(s.stint_number, s.compound) for s in out["AAA"]] == [(1, "SOFT"), (2, "HARD")]
    assert out["AAA"][0].gaps_to_car_ahead == [None, None]  # the leader has no car ahead
    assert out["BBB"][0].gaps_to_car_ahead == [pytest.approx(1.5)] * 4


def test_extract_stints_tolerates_missing_position_and_lap_time():
    rows = [lap_row("AAA", 1, None), lap_row("AAA", 2, 90.0)]
    (stint,) = extract_stints(fake_session(rows))["AAA"]
    assert stint.lap_times == [90.0]  # the lap with no time is not a pace sample
    assert stint.gaps_to_car_ahead == [None]


def test_extract_stints_empty_session():
    assert extract_stints(fake_session([])) == {}


def test_store_stints_fuel_corrects_races_but_not_qualifying(db_session):
    race, ids = _seed(db_session, ["R"], fake_session(_race_rows()))
    store_stints(race, db_session)
    fe = fuel_effect_for_race(4)
    stint2 = db_session.exec(select(Stint).where(Stint.driver == "AAA", Stint.stint_number == 2)).one()
    # laps 3 and 4 of a 4-lap race: 1 and 0 laps of fuel remaining.
    assert stint2.lap_times_json == [pytest.approx(90.0 - fe), pytest.approx(90.0)]

    quali = fake_session([lap_row("AAA", 1, 90.0), lap_row("AAA", 2, 90.0)])
    data, ids = _seed(db_session, ["Q"], quali, round=9)
    store_stints(data, db_session)
    q = db_session.exec(select(Stint).where(Stint.session_id == ids["Q"])).one()
    assert q.lap_times_json == [90.0, 90.0]


# --- segment: clean-lap counts and corner lookup --------------------------------------------------

def test_clean_lap_counts_per_driver_and_empty():
    rows = _rows() + [lap_row("AAA", 9, 90.0, accurate=False)]
    assert segment.clean_lap_counts(fake_session(rows)) == {"AAA": 3, "BBB": 3}
    assert segment.clean_lap_counts(fake_session([])) == {}
    assert len(segment.select_clean_laps(fake_session([]))) == 0


def test_get_corners_reads_circuit_info_with_letters():
    corners = segment.get_corners(fake_session([], corners=[(1, 100.0, ""), (1, 150.0, "A")]))
    assert [(c.number, c.distance, c.letter) for c in corners] == [(1, 100.0, ""), (1, 150.0, "A")]


def test_get_corners_without_circuit_info_returns_no_corners():
    assert segment.get_corners(fake_session([], corners=None)) == []


def test_get_corners_without_a_usable_fallback_returns_no_corners():
    """get_circuit_info() raises and the session lacks the metadata the resilient rebuild needs."""
    assert segment.get_corners(fake_session(_rows(), circuit_info_raises=True)) == []


class _Info:
    def __init__(self, fail: bool):
        self._fail = fail
        self.corners = pd.DataFrame({"Number": [7], "Distance": [700.0], "Letter": [""]})

    def add_marker_distance(self, reference_lap):
        if self._fail:
            raise ValueError("this lap's telemetry will not merge")


def _resilient_session():
    s = fake_session(_rows(), circuit_info_raises=True)
    s.session_info = {"Meeting": {"Circuit": {"Key": 1}}}
    s.event = types.SimpleNamespace(year=2026)
    return s


def test_get_corners_rebuilds_from_the_first_lap_that_merges(monkeypatch):
    infos = iter([_Info(fail=True), _Info(fail=False)])
    monkeypatch.setattr("fastf1.mvapi.get_circuit_info", lambda **_: next(infos))
    assert [(c.number, c.distance) for c in segment.get_corners(_resilient_session())] == [(7, 700.0)]


def test_get_corners_gives_up_after_bounded_attempts(monkeypatch):
    calls = []
    monkeypatch.setattr("fastf1.mvapi.get_circuit_info", lambda **_: calls.append(1) or _Info(fail=True))
    assert segment.get_corners(_resilient_session()) == []
    assert len(calls) == 6  # one attempt per accurate lap here; the cap of 8 bounds longer sessions
