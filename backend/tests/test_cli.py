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


def _fake_run_season(rounds, results):
    def fake(year, agent_runner=None, quali_agent_runner=None, max_workers=4, on_round_start=None, on_round_complete=None):
        from telogify.pipeline import RoundResult, SeasonRunResult

        for i, (rnd, result) in enumerate(zip(rounds, results), start=1):
            if on_round_start:
                on_round_start(rnd, i, len(rounds))
            if on_round_complete:
                on_round_complete(result, i, len(rounds))
        return SeasonRunResult(year=year, rounds=rounds, results=results)

    return fake


def test_run_weekend_season_all_ok_shows_table(monkeypatch):
    from telogify.pipeline import RoundResult

    monkeypatch.setattr("telogify.pipeline.season_rounds", lambda year: [1, 2])
    results = [
        RoundResult(round=1, ok=True, insight_count=3, quali_insight_count=2),
        RoundResult(round=2, ok=True, insight_count=3, quali_insight_count=2),
    ]
    monkeypatch.setattr("telogify.pipeline.run_season", _fake_run_season([1, 2], results))
    result = runner.invoke(cli.app, ["run-weekend", "2026"])
    out = plain(result.output)
    assert result.exit_code == 0
    assert "Summary" in out and "OK" in out and "Done" in out


def test_run_insights_season_one_failure_exits_nonzero(monkeypatch):
    from telogify.pipeline import RoundResult

    monkeypatch.setattr("telogify.pipeline.season_rounds", lambda year: [1, 2])
    monkeypatch.setattr("telogify.config.configured_llm_label", lambda: "openai / gpt-5.5")
    results = [
        RoundResult(round=1, ok=True, insight_count=3, quali_insight_count=2),
        RoundResult(round=2, ok=False, error="untraceable number(s): ['54.0']"),
    ]
    monkeypatch.setattr("telogify.pipeline.run_insights_season", _fake_run_season([1, 2], results))
    result = runner.invoke(cli.app, ["run-insights", "2026"])
    out = plain(result.output)
    assert result.exit_code == 1
    assert "FAILED" in out
    assert "untraceable number" in out
    assert "1 round(s) failed" in out


def test_list_insights_no_weekends(monkeypatch, test_engine):
    monkeypatch.setattr("telogify.db.engine", test_engine)
    result = runner.invoke(cli.app, ["list-insights"])
    assert result.exit_code == 0
    assert "No race weekends found" in plain(result.output)


def test_list_insights_renders_panel_and_escapes_brackets(monkeypatch, test_engine):
    from sqlmodel import Session

    from telogify.models import Insight, QualiInsight, RaceWeekend

    monkeypatch.setattr("telogify.db.engine", test_engine)
    with Session(test_engine) as db:
        wk = RaceWeekend(
            year=2026, round=8, circuit_name="Spielberg", country="Austria",
            event_name="Austrian Grand Prix",
        )
        db.add(wk)
        db.commit()
        db.refresh(wk)
        db.add(Insight(
            weekend_id=wk.id, slot=1, header="Ferrari [scuderia] led sector one",
            explanation_web="body text", explanation_email="e", source_tool_calls_json=[],
        ))
        db.add(QualiInsight(
            weekend_id=wk.id, slot=1, team="Mercedes", header="Mercedes swept every sector",
            explanation_web="qualifying body", explanation_email="qe", source_tool_calls_json=[],
        ))
        db.commit()

    result = runner.invoke(cli.app, ["list-insights", "2026"])
    out = plain(result.output)
    assert result.exit_code == 0
    assert "Austrian Grand Prix" in out
    assert "Ferrari [scuderia] led sector one" in out
    assert "Mercedes" in out and "swept every sector" in out


def test_list_insights_year_and_round_filters_to_one_weekend(monkeypatch, test_engine):
    from sqlmodel import Session

    from telogify.models import RaceWeekend

    monkeypatch.setattr("telogify.db.engine", test_engine)
    with Session(test_engine) as db:
        db.add(RaceWeekend(year=2026, round=8, circuit_name="X", country="Y", event_name="Round Eight GP"))
        db.add(RaceWeekend(year=2026, round=9, circuit_name="X", country="Y", event_name="Round Nine GP"))
        db.commit()

    result = runner.invoke(cli.app, ["list-insights", "2026", "9"])
    out = plain(result.output)
    assert result.exit_code == 0
    assert "Round Nine GP" in out
    assert "Round Eight GP" not in out


def test_list_insights_empty_weekend_shows_placeholders(monkeypatch, test_engine):
    from sqlmodel import Session

    from telogify.models import RaceWeekend

    monkeypatch.setattr("telogify.db.engine", test_engine)
    with Session(test_engine) as db:
        wk = RaceWeekend(year=2026, round=9, circuit_name="X", country="Y", event_name="Z GP")
        db.add(wk)
        db.commit()

    result = runner.invoke(cli.app, ["list-insights", "2026"])
    out = plain(result.output)
    assert result.exit_code == 0
    assert "no insights persisted" in out
    assert "none persisted" in out


def test_ingest_season_reports_per_round_and_summary(monkeypatch):
    monkeypatch.setattr("telogify.pipeline.season_rounds", lambda year: [1, 2, 3])

    def fake_run_ingest(year, round):
        if round == 2:
            raise RuntimeError("boom")

    monkeypatch.setattr("telogify.pipeline.run_ingest", fake_run_ingest)
    result = runner.invoke(cli.app, ["ingest", "2026"])
    out = plain(result.output)
    assert result.exit_code == 1
    assert "Summary" in out
    assert "boom" in out
    assert "1 round(s) failed" in out
