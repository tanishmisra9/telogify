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
