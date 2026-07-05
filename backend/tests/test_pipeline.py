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


def test_insights_fails_loud_after_max_attempts(db_session, monkeypatch):
    monkeypatch.setattr(pipeline, "engine", db_session.get_bind())
    monkeypatch.setattr(pipeline, "Session", lambda *_a, **_k: db_session)

    def runner(year, round, feedback=None):
        return _fake_messages(_BAD_INSIGHTS)

    with pytest.raises(RuntimeError, match="unsupported claims"):
        pipeline._insights({"year": 2025, "round": 13, "weekend_id": 999}, runner)


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

    state = pipeline.regen_insights(2025, 14, agent_runner=lambda y, r, feedback=None: _fake_messages(_GOOD_INSIGHTS))
    assert state["insight_count"] == 3
    assert called == [wk.id]  # candidates recomputed, ingest/analyze skipped


def test_regen_insights_errors_without_ingested_weekend(db_session, monkeypatch):
    monkeypatch.setattr(pipeline, "engine", db_session.get_bind())
    monkeypatch.setattr(pipeline, "Session", lambda *_a, **_k: db_session)
    monkeypatch.setattr(pipeline, "_weekend_id", lambda db, y, r: None)

    with pytest.raises(RuntimeError, match="Run run-weekend first"):
        pipeline.regen_insights(2025, 99, agent_runner=lambda *a, **k: None)


def test_pipeline_runs_phases_in_order(monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline, "_ingest", lambda s: calls.append("ingest") or {"weekend_id": 1})
    monkeypatch.setattr(pipeline, "_analyze", lambda s: calls.append("analyze") or {})
    monkeypatch.setattr(pipeline, "_candidates", lambda s: calls.append("candidates") or {})

    def fake_insights(s, runner):
        calls.append("insights")
        assert s["weekend_id"] == 1  # state threaded from ingest
        return {"insight_count": len(runner(s["year"], s["round"]))}

    monkeypatch.setattr(pipeline, "_insights", fake_insights)

    # agent_runner returns 3 fake "messages"; pipeline never calls Anthropic here.
    state = pipeline.run_weekend(2025, 11, agent_runner=lambda y, r: ["m1", "m2", "m3"])

    assert calls == ["ingest", "analyze", "candidates", "insights"]
    assert state["insight_count"] == 3


def test_run_season_runs_each_planned_round(monkeypatch):
    monkeypatch.setattr(pipeline, "season_rounds", lambda year, now=None: [1, 2, 3])
    calls = []

    def fake_run_weekend(year, round, agent_runner=None):
        calls.append(round)
        return {"insight_count": 3}

    monkeypatch.setattr(pipeline, "run_weekend", fake_run_weekend)

    summary = pipeline.run_season(2026)
    assert summary.rounds == [1, 2, 3]
    assert calls == [1, 2, 3]
    assert all(r.ok for r in summary.results)
    assert all(r.insight_count == 3 for r in summary.results)


def test_run_season_continues_after_failure(monkeypatch):
    monkeypatch.setattr(pipeline, "season_rounds", lambda year, now=None: [1, 2, 3])

    def fake_run_weekend(year, round, agent_runner=None):
        if round == 2:
            raise RuntimeError("guardrail failure")
        return {"insight_count": 3}

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
