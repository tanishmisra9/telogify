from telogify.ingest.stints import summarize_stint


def _lap(n, t, *, out=False, inn=False, acc=True, compound="MEDIUM"):
    return dict(
        lap_number=n, lap_time_s=t, compound=compound, is_outlap=out, is_inlap=inn, is_accurate=acc
    )


def test_summarize_stint_excludes_in_out_and_inaccurate():
    laps = [
        _lap(5, 95.0, out=True),   # outlap, excluded from pace
        _lap(6, 90.0),
        _lap(7, 90.5),
        _lap(8, 200.0, acc=False),  # inaccurate (e.g. SC), excluded
        _lap(9, 91.0),
        _lap(10, 96.0, inn=True),  # inlap, excluded
    ]
    s = summarize_stint(2, laps)

    assert s.stint_number == 2
    assert s.compound == "MEDIUM"
    assert s.lap_start == 5 and s.lap_end == 10  # full range retained
    assert s.lap_times == [90.0, 90.5, 91.0]
    assert abs(s.avg_pace - 90.5) < 1e-9


def test_summarize_stint_all_excluded_gives_none_pace():
    s = summarize_stint(1, [_lap(1, 100.0, out=True), _lap(2, 101.0, inn=True)])
    assert s.lap_times == []
    assert s.avg_pace is None
