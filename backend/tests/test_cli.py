"""Smoke tests for the CLI's rich-based output. Mocks telogify.pipeline so no real
ingest/LLM call ever happens; just checks each command runs cleanly and the key
content (not exact rich formatting) appears in the output.

rich's Console still emits ANSI escapes under Click/Typer's CliRunner (its terminal
detection is fixed at Console() construction time, which happens at module import,
before CliRunner redirects stdout), so assertions strip escape codes first rather
than asserting on raw output.
"""

import re

from typer.testing import CliRunner

from telogify import cli

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def plain(text: str) -> str:
    return _ANSI_RE.sub("", text)


def test_run_weekend_dry_run_lists_rounds(monkeypatch):
    monkeypatch.setattr("telogify.pipeline.season_rounds", lambda year: [1, 2, 3])
    result = runner.invoke(cli.app, ["run-weekend", "2026", "--dry-run"])
    assert result.exit_code == 0
    assert "1" in plain(result.output) and "2" in plain(result.output) and "3" in plain(result.output)


def test_run_weekend_no_completed_rounds(monkeypatch):
    monkeypatch.setattr("telogify.pipeline.season_rounds", lambda year: [])
    result = runner.invoke(cli.app, ["run-weekend", "2026"])
    assert result.exit_code == 0
    assert "No completed rounds found for 2026" in plain(result.output)


def test_run_insights_dry_run_lists_rounds(monkeypatch):
    monkeypatch.setattr("telogify.pipeline.season_rounds", lambda year: [4, 5])
    monkeypatch.setattr("telogify.config.configured_llm_label", lambda: "openai / gpt-5.5")
    result = runner.invoke(cli.app, ["run-insights", "2026", "--dry-run"])
    assert result.exit_code == 0
    assert "4" in plain(result.output) and "5" in plain(result.output)
    assert "gpt-5.5" in plain(result.output)


def test_ingest_dry_run_lists_rounds(monkeypatch):
    monkeypatch.setattr("telogify.pipeline.season_rounds", lambda year: [7])
    result = runner.invoke(cli.app, ["ingest", "2026", "--dry-run"])
    assert result.exit_code == 0
    assert "7" in plain(result.output)


def test_ingest_no_completed_rounds(monkeypatch):
    monkeypatch.setattr("telogify.pipeline.season_rounds", lambda year: [])
    result = runner.invoke(cli.app, ["ingest", "2026"])
    assert result.exit_code == 0
    assert "No completed rounds found for 2026" in plain(result.output)


def test_run_weekend_single_round_reports_counts(monkeypatch):
    monkeypatch.setattr(
        "telogify.pipeline.run_weekend",
        lambda year, round: {"insight_count": 3, "quali_insight_count": 2},
    )
    result = runner.invoke(cli.app, ["run-weekend", "2026", "8"])
    assert result.exit_code == 0
    out = plain(result.output)
    assert "Done" in out and "3" in out and "2" in out


def test_run_insights_single_round_reports_counts(monkeypatch):
    monkeypatch.setattr("telogify.config.configured_llm_label", lambda: "openai / gpt-5.5")
    monkeypatch.setattr(
        "telogify.pipeline.regen_insights",
        lambda year, round: {"insight_count": 3, "quali_insight_count": 2},
    )
    result = runner.invoke(cli.app, ["run-insights", "2026", "8"])
    assert result.exit_code == 0
    out = plain(result.output)
    assert "gpt-5.5" in out and "Done" in out and "3" in out and "2" in out


def test_ingest_single_round_done(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "telogify.pipeline.run_ingest", lambda year, round: calls.append((year, round))
    )
    result = runner.invoke(cli.app, ["ingest", "2026", "8"])
    assert result.exit_code == 0
    assert calls == [(2026, 8)]
    assert "Done" in plain(result.output)
