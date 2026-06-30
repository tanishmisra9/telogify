from telogify import pipeline


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
