from telogify.analysis.results_views import build_quali_segments, places_gained, segment_sizes


def _field(n=22, *, skip=()):
    """A 22-car field: P1 fastest. q1 = 80 + i*0.1, q2 for P1-16, q3 for P1-10 (Q3 times deliberately
    SLOWER than the same car's Q2 for P10, as seen in real data)."""
    rows = []
    for i in range(1, n + 1):
        rows.append({
            "driver": f"D{i:02d}", "constructor": f"T{(i + 1) // 2}", "position": i,
            "q1_s": 80 + i * 0.1,
            "q2_s": 79 + i * 0.1 if i <= 16 else None,
            "q3_s": 78 + i * 0.1 if i <= 10 else None,
        })
    for r in rows:
        if r["driver"] in skip:
            r["q1_s"] = r["q2_s"] = r["q3_s"] = None
            r["position"] = None
    return rows


def test_segment_sizes_for_22_and_20_cars_and_tiny_field():
    assert segment_sizes(22) == (16, 10)
    assert segment_sizes(20) == (15, 10)
    assert segment_sizes(3) == (3, 3)  # never negative or inverted


def test_membership_comes_from_position_not_from_which_times_exist():
    rows = _field()
    # D05 reached Q3 by position but set no Q3 time; D12 reached Q2 but set no Q2 time.
    rows[4]["q3_s"] = None
    rows[11]["q2_s"] = None
    segs = {s["name"]: s for s in build_quali_segments(rows, "Q")["segments"]}
    assert [s for s in segs] == ["Q3", "Q2", "Q1"]
    assert len(segs["Q3"]["rows"]) == 10 and len(segs["Q2"]["rows"]) == 16 and len(segs["Q1"]["rows"]) == 22
    d05 = next(r for r in segs["Q3"]["rows"] if r["driver"] == "D05")
    assert d05["time_s"] is None and d05["gap_to_fastest_s"] is None
    assert segs["Q3"]["rows"][-1]["driver"] == "D05"  # no time sorts last
    assert segs["Q2"]["rows"][-1]["driver"] == "D12"


def test_cut_is_slowest_advancer_and_gap_to_cut_sign():
    segs = {s["name"]: s for s in build_quali_segments(_field(), "Q")["segments"]}
    assert segs["Q3"]["cut_s"] is None and all(r["advanced"] is None for r in segs["Q3"]["rows"])
    # Q2 cut = P10's Q2 time (79 + 1.0); Q1 cut = P16's Q1 time (80 + 1.6)
    assert segs["Q2"]["cut_s"] == 80.0
    assert segs["Q1"]["cut_s"] == 81.6
    q2 = {r["driver"]: r for r in segs["Q2"]["rows"]}
    assert q2["D10"]["advanced"] is True and q2["D10"]["gap_to_cut_s"] == 0.0
    assert q2["D11"]["advanced"] is False and q2["D11"]["gap_to_cut_s"] == 0.1
    assert q2["D01"]["gap_to_cut_s"] < 0
    # every eliminated car is slower than the cut
    assert all(r["gap_to_cut_s"] > 0 for r in segs["Q1"]["rows"] if r["advanced"] is False)


def test_null_position_car_is_a_q1_no_time_row_only():
    segs = {s["name"]: s for s in build_quali_segments(_field(skip=("D22",)), "Q")["segments"]}
    q1 = segs["Q1"]["rows"]
    assert q1[-1]["driver"] == "D22" and q1[-1]["time_s"] is None and q1[-1]["advanced"] is False
    assert all(r["driver"] != "D22" for r in segs["Q2"]["rows"] + segs["Q3"]["rows"])


def test_sprint_quali_names_and_empty_when_no_segment_times():
    assert [s["name"] for s in build_quali_segments(_field(), "SQ")["segments"]] == ["SQ3", "SQ2", "SQ1"]
    empty = [{"driver": "A", "constructor": "X", "position": 1, "q1_s": None, "q2_s": None, "q3_s": None}]
    assert build_quali_segments(empty, "Q")["segments"] == []
    assert build_quali_segments([], "Q")["segments"] == []


def test_places_gained_only_for_classified_finishers_with_a_grid():
    assert places_gained(5, 2, "Finished") == 3
    assert places_gained(2, 5, "Lapped") == -3
    assert places_gained(1, 1, "Finished") == 0
    assert places_gained(5, 12, "Retired") is None  # a DNF is not "lost 7 places"
    assert places_gained(5, 20, "Did not start") is None
    assert places_gained(5, 7, "") is None  # degraded round: unknown, not guessed
    assert places_gained(5, 7, None) is None
    assert places_gained(None, 7, "Finished") is None  # no qualifying position
    assert places_gained(5, None, "Finished") is None
