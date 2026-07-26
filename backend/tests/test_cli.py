"""Smoke tests for the CLI's rich-based output. Mocks telogify.pipeline so no real
ingest/LLM call ever happens; just checks each command runs cleanly and the key
content (not exact rich formatting) appears in the output.

rich's Console still emits ANSI escapes under Click/Typer's CliRunner (its terminal
detection is fixed at Console() construction time, which happens at module import,
before CliRunner redirects stdout), so assertions strip escape codes first rather
than asserting on raw output.
"""

import re
import signal
import subprocess
import sys
import textwrap
import time
from datetime import datetime, timedelta

import pytest
from typer.testing import CliRunner

from telogify import cli
from telogify.analysis.schedule import Event
from telogify.ingest.loader import _STALE_AFTER

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
        lambda year, round, force=False: {"insight_count": 3, "quali_insight_count": 2},
    )
    result = runner.invoke(cli.app, ["run-weekend", "2026", "8"])
    assert result.exit_code == 0
    out = plain(result.output)
    assert "Done" in out and "3" in out and "2" in out


def test_run_weekend_single_round_passes_force_flag(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "telogify.pipeline.run_weekend",
        lambda year, round, force=False: calls.append(force) or {"insight_count": 3, "quali_insight_count": 2},
    )
    result = runner.invoke(cli.app, ["run-weekend", "2026", "8", "--force"])
    assert result.exit_code == 0
    assert calls == [True]


def test_run_weekend_single_round_defaults_force_false(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "telogify.pipeline.run_weekend",
        lambda year, round, force=False: calls.append(force) or {"insight_count": 3, "quali_insight_count": 2},
    )
    result = runner.invoke(cli.app, ["run-weekend", "2026", "8"])
    assert result.exit_code == 0
    assert calls == [False]


def test_run_insights_single_round_passes_force_flag(monkeypatch):
    monkeypatch.setattr("telogify.config.configured_llm_label", lambda: "openai / gpt-5.5")
    calls = []
    monkeypatch.setattr(
        "telogify.pipeline.regen_insights",
        lambda year, round, force=False: calls.append(force) or {"insight_count": 3, "quali_insight_count": 2},
    )
    result = runner.invoke(cli.app, ["run-insights", "2026", "8", "--force"])
    assert result.exit_code == 0
    assert calls == [True]


def test_run_insights_single_round_reports_counts(monkeypatch):
    monkeypatch.setattr("telogify.config.configured_llm_label", lambda: "openai / gpt-5.5")
    monkeypatch.setattr(
        "telogify.pipeline.regen_insights",
        lambda year, round, force=False: {"insight_count": 3, "quali_insight_count": 2},
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
    def fake(year, agent_runner=None, quali_agent_runner=None, max_workers=4, force=False, on_round_start=None, on_round_complete=None):
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


def test_resolve_poll_year_defaults_to_now_year():
    assert cli._resolve_poll_year(None, datetime(2027, 1, 5)) == 2027


def test_resolve_poll_year_uses_given_year():
    assert cli._resolve_poll_year(2026, datetime(2027, 1, 5)) == 2026


def test_poll_round_window_empty_events_is_clean_noop():
    assert cli._poll_round_window((), datetime(2026, 7, 20)) == []


def test_poll_round_window_off_season_between_years_is_clean_noop():
    # Non-empty schedule, but nothing falls in the window -- e.g. the gap between the last
    # round of one year and the first round of the next.
    now = datetime(2027, 1, 15)
    events = (
        Event(round=24, name="Season Finale", date=datetime(2026, 12, 7)),
        Event(round=1, name="Season Opener", date=datetime(2027, 3, 6)),
    )
    assert cli._poll_round_window(events, now) == []


def test_poll_round_window_includes_race_within_window():
    now = datetime(2026, 7, 20, 12, 0)
    events = (Event(round=12, name="A GP", date=now - timedelta(hours=2)),)
    assert cli._poll_round_window(events, now) == [12]


def test_poll_round_window_excludes_stale_race():
    now = datetime(2026, 7, 20, 12, 0)
    events = (Event(round=12, name="A GP", date=now - _STALE_AFTER - timedelta(minutes=1)),)
    assert cli._poll_round_window(events, now) == []


def test_poll_round_window_excludes_far_future_race():
    now = datetime(2026, 7, 20, 12, 0)
    events = (Event(round=12, name="A GP", date=now + timedelta(days=3, minutes=1)),)
    assert cli._poll_round_window(events, now) == []


def test_poll_round_window_back_to_back_rounds_both_included_sorted():
    now = datetime(2026, 7, 20, 12, 0)
    events = (
        Event(round=13, name="B GP", date=now + timedelta(days=1)),
        Event(round=12, name="A GP", date=now - timedelta(hours=1)),
    )
    assert cli._poll_round_window(events, now) == [12, 13]


def test_poll_round_window_excludes_round_zero():
    now = datetime(2026, 7, 20, 12, 0)
    events = (Event(round=0, name="Testing", date=now),)
    assert cli._poll_round_window(events, now) == []


def test_poll_schedule_fetch_empty_reports_distinctly_from_empty_window(monkeypatch):
    monkeypatch.setattr("telogify.analysis.schedule.fetch_season_schedule", lambda year: ())
    result = runner.invoke(cli.app, ["poll", "2026"])
    out = plain(result.output)
    assert result.exit_code == 0
    assert "Schedule fetch returned nothing" in out


def test_poll_empty_window_reports_distinctly_from_empty_schedule(monkeypatch):
    now = datetime.utcnow()
    stale_event = (Event(round=1, name="Old GP", date=now - _STALE_AFTER - timedelta(days=30)),)
    monkeypatch.setattr(
        "telogify.analysis.schedule.fetch_season_schedule", lambda year: stale_event
    )
    result = runner.invoke(cli.app, ["poll", "2026"])
    out = plain(result.output)
    assert result.exit_code == 0
    assert "no rounds in the current window" in out


def test_poll_happy_path_calls_run_weekend_without_force(monkeypatch):
    now = datetime.utcnow()
    ready_event = (Event(round=8, name="Ready GP", date=now - timedelta(hours=1)),)
    monkeypatch.setattr(
        "telogify.analysis.schedule.fetch_season_schedule", lambda year: ready_event
    )
    calls = []

    def fake_run_weekend(year, round):
        calls.append((year, round))
        return {"insight_count": 3, "quali_insight_count": 2}

    monkeypatch.setattr("telogify.pipeline.run_weekend", fake_run_weekend)
    result = runner.invoke(cli.app, ["poll", "2026"])
    assert result.exit_code == 0
    # Positional-only call, no `force` kwarg -- poll must never force-regenerate.
    assert calls == [(2026, 8)]


def test_poll_timeout_escapes_fastf1_soft_exceptions():
    """The highest-value test in this plan: fires a real SIGALRM inside FastF1's REAL
    @soft_exceptions decorator (not a hand-rolled mimic) and asserts _PollTimeout still
    propagates out. Imports the real decorator so a future fastf1 upgrade that changes its
    catch semantics fails this test rather than silently disarming the cap in production --
    fastf1 is unpinned in requirements.txt, so a Railway rebuild can move prod onto a
    different version with no code change."""
    from fastf1.logger import get_logger, soft_exceptions

    @soft_exceptions("test operation", "failed", get_logger("telogify-test"))
    def slow():
        time.sleep(3)

    old_handler = signal.signal(signal.SIGALRM, cli._raise_poll_timeout)
    signal.alarm(1)
    try:
        with pytest.raises(cli._PollTimeout):
            slow()
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


def test_poll_timeout_escapes_the_full_cli_invocation(monkeypatch):
    """Proves nothing in our own poll loop or Typer/Click's command-dispatch machinery catches
    _PollTimeout when driven through Click's CliRunner. NOTE the scope of this: CliRunner is a
    TEST harness, not the real deploy path -- Railway execs the installed `telogify` console
    script directly, not CliRunner, and CliRunner.invoke() deliberately suppresses Click's
    normal `sys.exit` (standalone_mode) to capture output instead. So this test only proves the
    exception survives Click's *test* harness. The real production call shape is covered
    separately by test_poll_timeout_survives_real_console_script_invocation below, which is
    the one that actually matters for what Railway will observe."""
    now = datetime.utcnow()
    ready_event = (Event(round=8, name="Ready GP", date=now - timedelta(hours=1)),)
    monkeypatch.setattr(
        "telogify.analysis.schedule.fetch_season_schedule", lambda year: ready_event
    )

    def hanging_run_weekend(year, round):
        time.sleep(2)

    monkeypatch.setattr("telogify.pipeline.run_weekend", hanging_run_weekend)
    monkeypatch.setattr(cli, "_POLL_TIMEOUT_S", 1)

    with pytest.raises(cli._PollTimeout):
        runner.invoke(cli.app, ["poll", "2026"], catch_exceptions=False)


def test_poll_timeout_survives_real_console_script_invocation():
    """The test that actually matters: Railway execs the INSTALLED `telogify` script, not
    CliRunner. Read `.venv/bin/telogify` -- setuptools generates exactly
    `sys.exit(app())` (verified this session), with no try/except of its own. Reproduce that
    literal call shape in a real subprocess (so a real process exit code is observable, unlike
    calling cli.app() in-process) with fetch_season_schedule/run_weekend faked out so this
    stays offline and fast -- no network, no DB, no LLM call.

    This is the same "silent by construction" risk category as the alarm-escape test above: a
    future typer/click upgrade that changes standalone_mode's exception handling, or a change
    to how setuptools generates the entry-point shim, needs to fail HERE to be caught. Without
    this test, that regression is invisible until someone notices a hung cron in production."""
    script = textwrap.dedent(
        """
        import sys
        import time
        from datetime import datetime, timedelta

        from telogify import cli
        from telogify.analysis.schedule import Event

        now = datetime.utcnow()
        ready_event = (Event(round=8, name="Ready GP", date=now - timedelta(hours=1)),)

        import telogify.analysis.schedule as schedule
        schedule.fetch_season_schedule = lambda year: ready_event

        import telogify.pipeline as pipeline

        def hanging_run_weekend(year, round):
            time.sleep(2)

        pipeline.run_weekend = hanging_run_weekend
        cli._POLL_TIMEOUT_S = 1

        sys.argv = ["telogify", "poll", "2026"]
        sys.exit(cli.app())
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=15
    )
    assert result.returncode != 0
    assert "_PollTimeout" in result.stderr
