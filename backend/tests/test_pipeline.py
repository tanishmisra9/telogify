import json

import pytest
from langchain_core.messages import AIMessage

from telogify import pipeline


def _fake_messages(insights: list[dict]) -> list:
    return [AIMessage(content=json.dumps(insights))]


_GOOD_INSIGHTS = [
    {"header": f"H{i}", "explanation_web": f"W{i}", "explanation_email": f"E{i}"}
    for i in range(1, 4)
]
_GOOD_QUALI_INSIGHTS = [
    {"team": f"Team{i}", "header": f"QH{i}", "explanation_web": f"QW{i}", "explanation_email": f"QE{i}"}
    for i in range(1, 3)
]
_BAD_INSIGHTS = [
    {"header": "Maiden win for Antonelli", "explanation_web": "W1", "explanation_email": "E1"},
    {"header": "H2", "explanation_web": "W2", "explanation_email": "E2"},
    {"header": "H3", "explanation_web": "W3", "explanation_email": "E3"},
]


def test_insights_persists_on_first_clean_attempt(db_session, monkeypatch):
    monkeypatch.setattr(pipeline, "engine", db_session.get_bind())
    monkeypatch.setattr(
        pipeline,
        "Session",
        lambda *_a, **_k: db_session,
    )
    from telogify.models import RaceWeekend

    wk = RaceWeekend(year=2025, round=11, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)

    calls = []

    def runner(year, round, feedback=None):
        calls.append(feedback)
        return _fake_messages(_GOOD_INSIGHTS)

    state = pipeline._insights({"year": 2025, "round": 11, "weekend_id": wk.id}, runner)
    assert state["insight_count"] == 3
    assert calls == [None]  # no retry needed


def test_insights_retries_then_succeeds(db_session, monkeypatch):
    monkeypatch.setattr(pipeline, "engine", db_session.get_bind())
    monkeypatch.setattr(pipeline, "Session", lambda *_a, **_k: db_session)
    from telogify.models import RaceWeekend

    wk = RaceWeekend(year=2025, round=12, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)

    attempts = []

    def runner(year, round, feedback=None):
        attempts.append(feedback)
        if len(attempts) == 1:
            return _fake_messages(_BAD_INSIGHTS)
        return _fake_messages(_GOOD_INSIGHTS)

    state = pipeline._insights({"year": 2025, "round": 12, "weekend_id": wk.id}, runner)
    assert state["insight_count"] == 3
    assert len(attempts) == 2
    assert attempts[0] is None
    assert "maiden" in str(attempts[1]).lower()


_SECOND_ROW_INSIGHTS = [
    {
        "header": "Ferrari lost ground from the second row",
        "explanation_web": "W1",
        "explanation_email": "E1",
    },
    {"header": "H2", "explanation_web": "W2", "explanation_email": "E2"},
    {"header": "H3", "explanation_web": "W3", "explanation_email": "E3"},
]


def test_insights_retry_feedback_names_second_row_fix(db_session, monkeypatch):
    monkeypatch.setattr(pipeline, "engine", db_session.get_bind())
    monkeypatch.setattr(pipeline, "Session", lambda *_a, **_k: db_session)
    from telogify.models import RaceWeekend

    wk = RaceWeekend(year=2025, round=15, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)

    attempts = []

    def runner(year, round, feedback=None):
        attempts.append(feedback)
        if len(attempts) == 1:
            return _fake_messages(_SECOND_ROW_INSIGHTS)
        return _fake_messages(_GOOD_INSIGHTS)

    state = pipeline._insights({"year": 2025, "round": 15, "weekend_id": wk.id}, runner)
    assert state["insight_count"] == 3
    assert len(attempts) == 2
    retry = attempts[1]
    assert "second row" in retry
    assert "started third" in retry
    assert "explanation_email" in retry


def test_insights_fails_loud_after_max_attempts(db_session, monkeypatch):
    monkeypatch.setattr(pipeline, "engine", db_session.get_bind())
    monkeypatch.setattr(pipeline, "Session", lambda *_a, **_k: db_session)

    def runner(year, round, feedback=None):
        return _fake_messages(_BAD_INSIGHTS)

    with pytest.raises(RuntimeError, match="unsupported claims"):
        pipeline._insights({"year": 2025, "round": 13, "weekend_id": 999}, runner)


def test_insights_fails_with_parse_error_when_json_never_valid(db_session, monkeypatch):
    monkeypatch.setattr(pipeline, "engine", db_session.get_bind())
    monkeypatch.setattr(pipeline, "Session", lambda *_a, **_k: db_session)

    def runner(year, round, feedback=None):
        return [AIMessage(content="not json at all")]

    with pytest.raises(RuntimeError, match="parseable JSON"):
        pipeline._insights({"year": 2025, "round": 17, "weekend_id": 999}, runner)


def test_regen_insights_recomputes_candidates_and_skips_ingest(db_session, monkeypatch):
    monkeypatch.setattr(pipeline, "engine", db_session.get_bind())
    monkeypatch.setattr(pipeline, "Session", lambda *_a, **_k: db_session)
    from telogify.models import RaceWeekend

    wk = RaceWeekend(year=2025, round=14, circuit_name="X", country="Y", event_name="Z")
    db_session.add(wk)
    db_session.commit()
    db_session.refresh(wk)

    called = []
    monkeypatch.setattr(pipeline, "_weekend_id", lambda db, y, r: wk.id)
    monkeypatch.setattr(pipeline, "compute_candidates", lambda wid, db: called.append(wid))
    # ingest/analyze must NOT run
    monkeypatch.setattr(pipeline, "_ingest", lambda s: called.append("ingest"))
    monkeypatch.setattr(pipeline, "_analyze", lambda s: called.append("analyze"))

    state = pipeline.regen_insights(
        2025,
        14,
        agent_runner=lambda y, r, feedback=None: _fake_messages(_GOOD_INSIGHTS),
        quali_agent_runner=lambda y, r, feedback=None: _fake_messages(_GOOD_QUALI_INSIGHTS),
    )
    assert state["insight_count"] == 3
    assert state["quali_insight_count"] == 2
    assert called == [wk.id]  # candidates recomputed, ingest/analyze skipped


def test_regen_insights_errors_without_ingested_weekend(db_session, monkeypatch):
    monkeypatch.setattr(pipeline, "engine", db_session.get_bind())
    monkeypatch.setattr(pipeline, "Session", lambda *_a, **_k: db_session)
    monkeypatch.setattr(pipeline, "_weekend_id", lambda db, y, r: None)

    with pytest.raises(RuntimeError, match="Run run-weekend first"):
        pipeline.regen_insights(2025, 99, agent_runner=lambda *a, **k: None)


def test_flag_all_flags_each_insight_independently():
    flagged = pipeline._flag_all([
        {"header": "Clean insight", "explanation_web": "W1", "explanation_email": "E1"},
        {"header": "Maiden win", "explanation_web": "W2", "explanation_email": "E2"},
        {"header": "H3", "explanation_web": "W3", "explanation_email": "E3"},
    ])
    assert 1 not in flagged
    assert "maiden" in flagged[2]


def test_pipeline_runs_phases_in_order(monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline, "_ingest", lambda s: calls.append("ingest") or {"weekend_id": 1})
    monkeypatch.setattr(pipeline, "_analyze", lambda s: calls.append("analyze") or {})
    monkeypatch.setattr(pipeline, "_candidates", lambda s: calls.append("candidates") or {})

    def fake_insights(s, runner):
        calls.append("insights")
        assert s["weekend_id"] == 1  # state threaded from ingest
        return {"insight_count": len(runner(s["year"], s["round"]))}

    def fake_quali_insights(s, runner):
        calls.append("quali_insights")
        assert s["weekend_id"] == 1
        return {"quali_insight_count": len(runner(s["year"], s["round"]))}

    monkeypatch.setattr(pipeline, "_insights", fake_insights)
    monkeypatch.setattr(pipeline, "_quali_insights", fake_quali_insights)

    # agent_runners return fake "messages"; pipeline never calls Anthropic here.
    state = pipeline.run_weekend(
        2025,
        11,
        agent_runner=lambda y, r: ["m1", "m2", "m3"],
        quali_agent_runner=lambda y, r: ["m1", "m2"],
    )

    assert calls == ["ingest", "analyze", "candidates", "insights", "quali_insights"]
    assert state["insight_count"] == 3
    assert state["quali_insight_count"] == 2


def test_run_season_runs_each_planned_round(monkeypatch):
    monkeypatch.setattr(pipeline, "season_rounds", lambda year, now=None: [1, 2, 3])
    calls = []

    def fake_run_weekend(year, round, agent_runner=None, quali_agent_runner=None):
        calls.append(round)
        return {"insight_count": 3, "quali_insight_count": 2}

    monkeypatch.setattr(pipeline, "run_weekend", fake_run_weekend)

    summary = pipeline.run_season(2026)
    assert summary.rounds == [1, 2, 3]
    assert calls == [1, 2, 3]
    assert all(r.ok for r in summary.results)
    assert all(r.insight_count == 3 for r in summary.results)


def test_run_season_continues_after_failure(monkeypatch):
    monkeypatch.setattr(pipeline, "season_rounds", lambda year, now=None: [1, 2, 3])

    def fake_run_weekend(year, round, agent_runner=None, quali_agent_runner=None):
        if round == 2:
            raise RuntimeError("guardrail failure")
        return {"insight_count": 3, "quali_insight_count": 2}

    monkeypatch.setattr(pipeline, "run_weekend", fake_run_weekend)

    summary = pipeline.run_season(2026)
    assert len(summary.results) == 3
    assert summary.results[0].ok
    assert not summary.results[1].ok
    assert summary.results[1].error == "guardrail failure"
    assert summary.results[2].ok


def test_run_season_empty_rounds_skips_pipeline(monkeypatch):
    monkeypatch.setattr(pipeline, "season_rounds", lambda year, now=None: [])
    called = []
    monkeypatch.setattr(pipeline, "run_weekend", lambda *a, **k: called.append(1))

    summary = pipeline.run_season(2026)
    assert summary.rounds == []
    assert summary.results == []
    assert called == []


def test_run_insights_season_calls_regen_not_full_pipeline(monkeypatch):
    monkeypatch.setattr(pipeline, "season_rounds", lambda year, now=None: [1, 2, 3])
    regen_calls = []
    ingest_calls = []

    def fake_regen(year, round, agent_runner=None, quali_agent_runner=None):
        regen_calls.append(round)
        return {"insight_count": 3, "quali_insight_count": 2}

    monkeypatch.setattr(pipeline, "regen_insights", fake_regen)
    monkeypatch.setattr(pipeline, "run_weekend", lambda *a, **k: ingest_calls.append(1))
    monkeypatch.setattr(pipeline, "_ingest", lambda s: ingest_calls.append("ingest"))

    summary = pipeline.run_insights_season(2026)
    assert summary.rounds == [1, 2, 3]
    assert regen_calls == [1, 2, 3]
    assert ingest_calls == []
    assert all(r.ok for r in summary.results)


def test_run_insights_season_continues_after_failure(monkeypatch):
    monkeypatch.setattr(pipeline, "season_rounds", lambda year, now=None: [1, 2, 3])

    def fake_regen(year, round, agent_runner=None, quali_agent_runner=None):
        if round == 2:
            raise RuntimeError("guardrail failure")
        return {"insight_count": 3, "quali_insight_count": 2}

    monkeypatch.setattr(pipeline, "regen_insights", fake_regen)

    summary = pipeline.run_insights_season(2026)
    assert len(summary.results) == 3
    assert summary.results[0].ok
    assert not summary.results[1].ok
    assert summary.results[1].error == "guardrail failure"
    assert summary.results[2].ok


def test_run_insights_season_empty_rounds_skips_regen(monkeypatch):
    monkeypatch.setattr(pipeline, "season_rounds", lambda year, now=None: [])
    called = []
    monkeypatch.setattr(pipeline, "regen_insights", lambda *a, **k: called.append(1))

    summary = pipeline.run_insights_season(2026)
    assert summary.rounds == []
    assert summary.results == []
    assert called == []


def test_run_season_progress_callbacks_fire_in_order(monkeypatch):
    monkeypatch.setattr(pipeline, "season_rounds", lambda year, now=None: [1, 2, 3])
    events = []

    def fake_run_weekend(year, round, agent_runner=None, quali_agent_runner=None):
        events.append(("work", round))
        return {"insight_count": 3, "quali_insight_count": 2}

    monkeypatch.setattr(pipeline, "run_weekend", fake_run_weekend)

    def on_start(rnd, index, total):
        events.append(("start", rnd, index, total))

    def on_complete(result, index, total):
        events.append(("complete", result.round, result.ok, index, total))

    summary = pipeline.run_season(
        2026,
        on_round_start=on_start,
        on_round_complete=on_complete,
    )
    assert all(r.ok for r in summary.results)
    assert events == [
        ("start", 1, 1, 3),
        ("work", 1),
        ("complete", 1, True, 1, 3),
        ("start", 2, 2, 3),
        ("work", 2),
        ("complete", 2, True, 2, 3),
        ("start", 3, 3, 3),
        ("work", 3),
        ("complete", 3, True, 3, 3),
    ]


def test_run_insights_season_progress_callbacks_on_failure(monkeypatch):
    monkeypatch.setattr(pipeline, "season_rounds", lambda year, now=None: [1, 2, 3])
    events = []

    def fake_regen(year, round, agent_runner=None, quali_agent_runner=None):
        if round == 2:
            raise RuntimeError("guardrail failure")
        return {"insight_count": 3, "quali_insight_count": 2}

    monkeypatch.setattr(pipeline, "regen_insights", fake_regen)

    def on_start(rnd, index, total):
        events.append(("start", rnd, index, total))

    def on_complete(result, index, total):
        events.append(("complete", result.round, result.ok, index, total))

    summary = pipeline.run_insights_season(
        2026,
        on_round_start=on_start,
        on_round_complete=on_complete,
    )
    assert len(summary.results) == 3
    assert events == [
        ("start", 1, 1, 3),
        ("complete", 1, True, 1, 3),
        ("start", 2, 2, 3),
        ("complete", 2, False, 2, 3),
        ("start", 3, 3, 3),
        ("complete", 3, True, 3, 3),
    ]
