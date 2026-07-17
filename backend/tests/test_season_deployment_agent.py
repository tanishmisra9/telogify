import json

import pytest

from telogify.agent.season_deployment import (
    build_metrics_payload,
    generate_season_deployment_verdicts,
    persist_season_deployment,
)
from telogify.models import SeasonDeploymentInsight


def _scatter():
    # Ferrari (works team) alone carries "Ferrari" PU; Mercedes carries Mercedes+McLaren.
    punch, hold = 2.0, -0.5
    ferrari_points = [[255.0, punch]] * 5 + [[265.0, punch]] * 5 + [[295.0, hold]] * 5 + [[305.0, hold]] * 5
    merc_points = [[255.0, 1.0]] * 5 + [[265.0, 1.0]] * 5 + [[295.0, -2.0]] * 5 + [[305.0, -2.0]] * 5
    return {
        "Ferrari": ferrari_points,
        "Mercedes": merc_points,
        "McLaren": merc_points,
    }


def test_build_metrics_payload_ranks_and_shapes_rows():
    metrics = build_metrics_payload(_scatter())
    assert [m["pu"] for m in metrics] == ["Ferrari", "Mercedes"]
    assert metrics[0]["rank"] == 1
    assert metrics[1]["rank"] == 2
    assert metrics[1]["teams"] == ["Mercedes", "McLaren"]


def test_build_metrics_payload_empty_scatter_returns_empty():
    assert build_metrics_payload({}) == []


def _good_verdicts(metrics):
    return [
        {
            "pu": m["pu"],
            "header": f"{m['pu']} verdict",
            "explanation_web": f"{m['pu']} cars held {m['punch_accel_ms2_250_290_kmh']} m/s2 through the mid-range.",
        }
        for m in metrics
    ]


def test_generate_verdicts_succeeds_on_first_clean_attempt():
    calls = []

    def fake_runner(metrics, feedback=None):
        calls.append(feedback)
        return json.dumps(_good_verdicts(metrics))

    verdicts, metrics = generate_season_deployment_verdicts(_scatter(), agent_runner=fake_runner)
    assert len(calls) == 1
    assert calls[0] is None
    assert [v["pu"] for v in verdicts] == ["Ferrari", "Mercedes"]
    assert len(metrics) == 2


def test_generate_verdicts_empty_scatter_returns_empty_without_calling_llm():
    def fail_runner(metrics, feedback=None):
        raise AssertionError("should not be called")

    verdicts, metrics = generate_season_deployment_verdicts({}, agent_runner=fail_runner)
    assert verdicts == [] and metrics == []


def test_generate_verdicts_retries_on_untraceable_number_then_succeeds():
    attempts = {"n": 0}

    def fake_runner(metrics, feedback=None):
        attempts["n"] += 1
        if attempts["n"] == 1:
            bad = _good_verdicts(metrics)
            bad[0]["explanation_web"] = "Invented a made-up 99.987 m/s2 figure."
            return json.dumps(bad)
        return json.dumps(_good_verdicts(metrics))

    verdicts, metrics = generate_season_deployment_verdicts(_scatter(), agent_runner=fake_runner)
    assert attempts["n"] == 2
    assert len(verdicts) == 2


def test_generate_verdicts_retries_on_jargon_then_succeeds():
    attempts = {"n": 0}

    def fake_runner(metrics, feedback=None):
        attempts["n"] += 1
        if attempts["n"] == 1:
            bad = _good_verdicts(metrics)
            bad[0]["header"] = "The candidate benchmark shows a strong result"
            return json.dumps(bad)
        return json.dumps(_good_verdicts(metrics))

    verdicts, metrics = generate_season_deployment_verdicts(_scatter(), agent_runner=fake_runner)
    assert attempts["n"] == 2


def test_generate_verdicts_fails_loud_after_max_attempts():
    def bad_runner(metrics, feedback=None):
        bad = _good_verdicts(metrics)
        bad[0]["explanation_web"] = "Invented a made-up 99.987 m/s2 figure."
        return json.dumps(bad)

    with pytest.raises(RuntimeError):
        generate_season_deployment_verdicts(_scatter(), agent_runner=bad_runner)


def test_generate_verdicts_retries_on_wrong_row_count():
    attempts = {"n": 0}

    def fake_runner(metrics, feedback=None):
        attempts["n"] += 1
        if attempts["n"] == 1:
            return json.dumps(_good_verdicts(metrics)[:1])  # missing a row
        return json.dumps(_good_verdicts(metrics))

    verdicts, metrics = generate_season_deployment_verdicts(_scatter(), agent_runner=fake_runner)
    assert attempts["n"] == 2
    assert len(verdicts) == 2


def test_persist_season_deployment_idempotent(db_session):
    from sqlmodel import select

    metrics = build_metrics_payload(_scatter())
    verdicts = _good_verdicts(metrics)

    persist_season_deployment(2026, verdicts, metrics, db_session)
    rows = db_session.exec(select(SeasonDeploymentInsight).where(SeasonDeploymentInsight.year == 2026)).all()
    assert len(rows) == 2
    assert rows[0].rank == 1 and rows[0].pu_name == "Ferrari"

    # Re-running deletes and reinserts rather than duplicating.
    persist_season_deployment(2026, verdicts, metrics, db_session)
    rows = db_session.exec(select(SeasonDeploymentInsight).where(SeasonDeploymentInsight.year == 2026)).all()
    assert len(rows) == 2
