import json
import types

import pytest
from langchain_core.messages import SystemMessage

from telogify.agent.season_deployment import (
    _MAX_ATTEMPTS,
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


# --- retry feedback: each failure mode must tell the model what to fix -----------------------------

def _run_with_replies(replies):
    """Drive generate_season_deployment_verdicts with scripted replies; returns (result, feedbacks).
    `replies` are strings or callables(metrics) -> string, consumed one per attempt."""
    feedbacks = []
    queue = iter(replies)

    def runner(metrics, feedback=None):
        feedbacks.append(feedback)
        nxt = next(queue)
        return nxt(metrics) if callable(nxt) else nxt

    return generate_season_deployment_verdicts(_scatter(), agent_runner=runner), feedbacks


def _good(metrics):
    return json.dumps(_good_verdicts(metrics))


def test_retry_after_no_json_array_says_so_and_asks_for_a_raw_array():
    (verdicts, _), feedbacks = _run_with_replies(["Sorry, here are my thoughts in prose.", _good])
    assert len(verdicts) == 2
    assert feedbacks[0] is None
    assert "no JSON array" in feedbacks[1] and "exactly 2 objects" in feedbacks[1]


def test_retry_after_unparseable_json_carries_the_parse_error():
    (verdicts, _), feedbacks = _run_with_replies(["[not valid json]", _good])
    assert len(verdicts) == 2
    assert "did not parse" in feedbacks[1]


def test_retry_after_missing_keys_names_the_rows_that_lack_them():
    def missing_header(metrics):
        rows = _good_verdicts(metrics)
        del rows[1]["header"]
        return json.dumps(rows)

    (verdicts, _), feedbacks = _run_with_replies([missing_header, _good])
    assert len(verdicts) == 2
    assert "missing required keys" in feedbacks[1] and "Mercedes" in feedbacks[1]
    assert "Ferrari" not in feedbacks[1]  # only the offending row is named


@pytest.mark.parametrize("bad_rows", ["[1, 2]", "[null, null]", '["pu header explanation_web", "pu header explanation_web"]'])
def test_non_object_rows_get_retry_feedback_instead_of_crashing(bad_rows):
    """A row that is not a JSON object (a number, null, or a string that merely contains the key
    names) used to raise TypeError on the first attempt, skipping the retry loop entirely."""
    (verdicts, _), feedbacks = _run_with_replies([bad_rows, _good])
    assert len(verdicts) == 2
    assert "missing required keys" in feedbacks[1]


def test_rows_returned_in_the_wrong_order_are_rejected_not_stored_under_the_wrong_pu():
    """Persist pairs verdicts to metrics by position. A swapped pair would publish Mercedes's
    verdict under Ferrari's name and rank, so the order must be enforced before persisting."""
    (verdicts, _), feedbacks = _run_with_replies([lambda m: json.dumps(_good_verdicts(m)[::-1]), _good])
    assert [v["pu"] for v in verdicts] == ["Ferrari", "Mercedes"]
    assert "same order" in feedbacks[1] and "Ferrari" in feedbacks[1] and "Mercedes" in feedbacks[1]


def test_a_duplicated_or_unknown_pu_is_rejected():
    def duplicated(metrics):
        rows = _good_verdicts(metrics)
        rows[1]["pu"] = rows[0]["pu"]
        return json.dumps(rows)

    def unknown(metrics):
        rows = _good_verdicts(metrics)
        rows[1]["pu"] = "Honda"
        return json.dumps(rows)

    for bad in (duplicated, unknown):
        (verdicts, _), feedbacks = _run_with_replies([bad, _good])
        assert [v["pu"] for v in verdicts] == ["Ferrari", "Mercedes"]
        assert "same order" in feedbacks[1]


@pytest.mark.parametrize("field,value", [("header", None), ("header", ""), ("explanation_web", 5), ("explanation_web", "   ")])
def test_blank_or_non_text_verdict_values_are_rejected_before_persist(field, value):
    """A null/number would raise AttributeError in strip_em_dashes AFTER the LLM spend; a blank
    string would publish an empty verdict."""
    def bad(metrics):
        rows = _good_verdicts(metrics)
        rows[0][field] = value
        return json.dumps(rows)

    (verdicts, _), feedbacks = _run_with_replies([bad, _good])
    assert all(isinstance(v["header"], str) and v["header"].strip() for v in verdicts)
    assert "non-empty text" in feedbacks[1] and "Ferrari" in feedbacks[1]


def test_retry_after_wrong_row_count_reports_expected_and_got():
    (_, _), feedbacks = _run_with_replies([lambda m: json.dumps(_good_verdicts(m)[:1]), _good])
    assert "Expected exactly 2 objects" in feedbacks[1] and "got 1" in feedbacks[1]


def test_validation_failure_feedback_lists_the_issue_and_demands_a_full_rewrite():
    def invented(metrics):
        rows = _good_verdicts(metrics)
        rows[0]["explanation_web"] = "Invented a made-up 99.987 m/s2 figure."
        return json.dumps(rows)

    (_, _), feedbacks = _run_with_replies([invented, _good])
    assert "99.987" in feedbacks[1] and "Rewrite ALL verdicts" in feedbacks[1]


def test_never_clean_output_raises_after_exactly_max_attempts():
    calls = []

    def runner(metrics, feedback=None):
        calls.append(feedback)
        return "no array here"

    with pytest.raises(RuntimeError, match=f"within {_MAX_ATTEMPTS} attempts"):
        generate_season_deployment_verdicts(_scatter(), agent_runner=runner)
    assert len(calls) == _MAX_ATTEMPTS


# --- _content_text: Anthropic returns content blocks, OpenAI a plain string --------------------------

def test_content_text_flattens_every_shape_a_provider_returns():
    from telogify.agent.season_deployment import _content_text

    assert _content_text("plain") == "plain"
    assert _content_text([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]) == "ab"
    assert _content_text([{"type": "tool_use"}, "raw"]) == "raw"  # a block with no text adds nothing


# --- the default runner: the one place this module calls an LLM (stubbed here) -----------------------

class _FakeProvider:
    def __init__(self, reply):
        self.seen = []
        self._reply = reply

    def build_model(self):
        outer = self

        class Model:
            def invoke(self, messages):
                outer.seen.append(messages)
                return types.SimpleNamespace(content=outer._reply)

        return Model()

    def build_system_message(self, prompt):
        return SystemMessage(content=prompt)


def test_default_runner_sends_the_system_prompt_and_the_metrics_json(monkeypatch):
    from telogify.agent.season_deployment import SYSTEM_PROMPT, _default_agent_runner

    provider = _FakeProvider([{"type": "text", "text": "[]"}])
    monkeypatch.setattr("telogify.agent.season_deployment.resolve_provider", lambda: provider)
    metrics = [{"rank": 1, "pu": "Ferrari"}]

    assert _default_agent_runner(metrics) == "[]"
    system, human = provider.seen[0]
    assert system.content == SYSTEM_PROMPT
    assert json.dumps(metrics, indent=2) in human.content
    assert "Rewrite" not in human.content  # no feedback on the first attempt


def test_default_runner_appends_validation_feedback_on_a_retry(monkeypatch):
    from telogify.agent.season_deployment import _default_agent_runner

    provider = _FakeProvider("[]")
    monkeypatch.setattr("telogify.agent.season_deployment.resolve_provider", lambda: provider)
    _default_agent_runner([{"rank": 1, "pu": "Ferrari"}], feedback="Fix the number 9.9.")
    assert provider.seen[0][1].content.endswith("Fix the number 9.9.")


def test_generate_uses_the_default_runner_when_none_is_injected(monkeypatch):
    metrics = build_metrics_payload(_scatter())
    provider = _FakeProvider(json.dumps(_good_verdicts(metrics)))
    monkeypatch.setattr("telogify.agent.season_deployment.resolve_provider", lambda: provider)
    verdicts, _ = generate_season_deployment_verdicts(_scatter())
    assert [v["pu"] for v in verdicts] == ["Ferrari", "Mercedes"]
    assert len(provider.seen) == 1


# --- persist: the house rules applied on write -------------------------------------------------------

def test_persist_strips_em_dashes_rounds_prose_and_stamps_provenance(db_session, monkeypatch):
    from sqlmodel import select

    from telogify.agent.season_deployment import PROMPT_VERSION

    monkeypatch.setattr("telogify.agent.season_deployment.configured_llm_label", lambda: "openai / test-model")
    metrics = build_metrics_payload(_scatter())
    verdicts = _good_verdicts(metrics)
    verdicts[0]["header"] = "Ferrari leads \u2014 clearly"
    verdicts[0]["explanation_web"] = "Cars held 2.00000 m/s2 \u2014 the best."

    persist_season_deployment(2026, verdicts, metrics, db_session)
    row = db_session.exec(select(SeasonDeploymentInsight).where(
        SeasonDeploymentInsight.year == 2026, SeasonDeploymentInsight.rank == 1)).one()
    assert "\u2014" not in row.header and "\u2014" not in row.explanation_web
    assert row.model_used == "openai / test-model"
    assert row.prompt_version == PROMPT_VERSION
    assert row.source_metrics_json["pu"] == "Ferrari"
    assert row.teams_json == metrics[0]["teams"]


def test_persist_only_replaces_the_requested_year(db_session):
    from sqlmodel import select

    metrics = build_metrics_payload(_scatter())
    persist_season_deployment(2025, _good_verdicts(metrics), metrics, db_session)
    persist_season_deployment(2026, _good_verdicts(metrics), metrics, db_session)
    persist_season_deployment(2026, _good_verdicts(metrics), metrics, db_session)
    years = [r.year for r in db_session.exec(select(SeasonDeploymentInsight)).all()]
    assert sorted(years) == [2025, 2025, 2026, 2026]
