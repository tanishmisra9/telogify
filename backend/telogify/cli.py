"""Telogify CLI. Manual triggers only (no scheduler)."""

import logging
import signal
import time
from datetime import datetime, timedelta

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.status import Status
from rich.table import Table

from telogify.pipeline import RoundResult

# Plain "%(message)s" so pipeline.logger's insight-retry diagnostics print exactly as they
# did as bare print()s; the entry point is telogify.cli:app (see pyproject.toml), not
# __main__, so this must run at import time to take effect for the installed command.
logging.basicConfig(level=logging.INFO, format="%(message)s")

# `telogify poll`'s wall-clock cap. Sized for a HANG, not a slow-but-real run: with no
# FASTF1_CACHE volume every run is cold, and a cold sprint weekend is 5 sessions, so a
# legitimate run can plausibly reach 45-75 min.
_POLL_TIMEOUT_S = 90 * 60


class _PollTimeout(BaseException):
    """Deliberately BaseException, NOT Exception: FastF1's `@soft_exceptions` (and our own
    ingest extractors) catch `except Exception` broadly, which would silently swallow an
    Exception-derived alarm and let the wrapped call return normally -- i.e. the cap would
    become invisible rather than merely ineffective, restoring the exact indefinite-hang
    scenario it exists to prevent. Verified empirically that a BaseException subclass escapes
    `@soft_exceptions` cleanly and that neither `fastf1/` nor `telogify/` catches
    `BaseException` or uses a bare `except:` anywhere."""


def _raise_poll_timeout(signum, frame) -> None:
    raise _PollTimeout(f"telogify poll exceeded its {_POLL_TIMEOUT_S}s hard cap")


app = typer.Typer(
    add_completion=False,
    help="Telogify: 3 quantified telemetry insights per F1 race weekend.",
)
console = Console(highlight=False)


def _format_elapsed(seconds: float) -> str:
    if seconds >= 60:
        minutes, rest = divmod(seconds, 60)
        return f"{int(minutes)}m {rest:.1f}s"
    return f"{seconds:.1f}s"


# Keyed by round number, so concurrent per-round writes (run-insights' thread pool) never
# collide. Spinners (_round_statuses) are only used by the sequential run-weekend path; rich's
# Live can't render several at once, so run-insights uses _on_round_start_line instead.
_round_start_times: dict[int, float] = {}
_round_elapsed: dict[int, str] = {}
_round_statuses: dict[int, Status] = {}


def _on_round_start(round: int, index: int, total: int) -> None:
    _round_start_times[round] = time.monotonic()
    status = console.status(f"[bold cyan]round {round} ({index}/{total}): running...[/bold cyan]")
    status.start()
    _round_statuses[round] = status


def _on_round_start_line(round: int, index: int, total: int) -> None:
    """Spinner-free start for the parallel run-insights pool (concurrent spinners can't coexist)."""
    _round_start_times[round] = time.monotonic()
    console.print(f"  [cyan]→[/cyan] round [bold]{round}[/bold] running...")


def _on_round_complete(result: RoundResult, index: int, total: int) -> None:
    status = _round_statuses.pop(result.round, None)
    if status is not None:
        status.stop()
    started = _round_start_times.pop(result.round, None)
    elapsed = _format_elapsed(time.monotonic() - started) if started is not None else "?"
    _round_elapsed[result.round] = elapsed
    if result.ok:
        console.print(
            f"  [green]✓[/green] round [bold]{result.round}[/bold] ({index}/{total}): "
            f"[bold]{result.insight_count}[/bold] insight(s), "
            f"[bold]{result.quali_insight_count}[/bold] qualifying insight(s) persisted [dim]({elapsed})[/dim]"
        )
    else:
        console.print(
            f"  [red]✗[/red] round [bold]{result.round}[/bold] ({index}/{total}): "
            f"[red]failed[/red] [dim]({elapsed})[/dim] - {escape(result.error or '')}"
        )


def _print_failures(failed: list[tuple[int, str]]) -> None:
    """failed: [(round, error), ...]. Shared tail for every season-loop summary."""
    console.print()
    console.print("[bold red]Failures:[/bold red]")
    for round_number, error in failed:
        console.print(f"  [bold]R{round_number}[/bold]: {escape(error)}")
    console.print(f"\n[red]{len(failed)} round(s) failed.[/red]")


def _echo_llm_model() -> None:
    from telogify.config import configured_llm_label

    console.print(f"[bold]Model:[/bold] [cyan]{escape(configured_llm_label())}[/cyan]")


def _echo_no_completed_rounds(year: int) -> None:
    console.print(f"[yellow]No completed rounds found for {year}.[/yellow]")


def _echo_dry_run_rounds(year: int, rounds: list[int]) -> None:
    round_list = ", ".join(str(r) for r in rounds)
    console.print(
        f"[bold]{year}[/bold] completed rounds [dim]({len(rounds)})[/dim]: [cyan]{round_list}[/cyan]"
    )


def _echo_season_final_summary(summary) -> None:
    """Aggregate summary, as a table, after all rounds have been logged live."""
    console.print()
    table = Table(title="Summary")
    table.add_column("Round", justify="right")
    table.add_column("Status")
    table.add_column("Insights", justify="right")
    table.add_column("Qualifying", justify="right")
    table.add_column("Time", justify="right")

    failed: list[tuple[int, str]] = []
    for result in summary.results:
        elapsed = _round_elapsed.pop(result.round, "?")
        if result.ok:
            table.add_row(
                str(result.round), "[green]OK[/green]",
                str(result.insight_count), str(result.quali_insight_count), elapsed,
            )
        else:
            table.add_row(str(result.round), "[red]FAILED[/red]", "-", "-", elapsed)
            failed.append((result.round, result.error or ""))
    console.print(table)

    if failed:
        _print_failures(failed)
        raise typer.Exit(code=1)

    console.print(f"\n[green]Done:[/green] {len(summary.results)} round(s) completed.")


def _report_insights_done(state: dict, elapsed: str) -> None:
    insight_count = state.get("insight_count", 0)
    quali_insight_count = state.get("quali_insight_count", 0)
    console.print(
        f"[green]Done:[/green] persisted [bold]{insight_count}[/bold] insights, "
        f"[bold]{quali_insight_count}[/bold] qualifying insights [dim]({elapsed})[/dim]."
    )
    session_types = state.get("session_types")
    # Zero counts are ambiguous on their own: they also mean "already fully generated on a
    # prior call, nothing new to do" (the pipeline's insights/quali_insights graph nodes
    # short-circuit to {} in that case, so the key is simply never set -- not a sign anything
    # is actually pending). Only genuinely "still in progress" once neither R nor Q -- the
    # sessions that gate generation -- has been ingested at all.
    if (
        insight_count == 0
        and quali_insight_count == 0
        and session_types
        and "R" not in session_types
        and "Q" not in session_types
    ):
        console.print(
            f"[yellow]Race weekend still in progress[/yellow] "
            f"(sessions ingested: {', '.join(session_types)}); insights not ready yet."
        )


def _run_insights_one(year: int, round: int, force: bool = False) -> None:
    from telogify.pipeline import regen_insights

    _echo_llm_model()
    started = time.monotonic()
    with console.status(f"[bold cyan]Regenerating insights for {year} round {round}...[/bold cyan]"):
        state = regen_insights(year, round, force=force)
    elapsed = _format_elapsed(time.monotonic() - started)
    _report_insights_done(state, elapsed)


@app.command("run-weekend")
def run_weekend_cmd(
    year: int,
    round: int | None = typer.Argument(
        None, help="Round number; omit to run all completed rounds for the year."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="List completed rounds only; do not run the pipeline."
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Re-ingest already-ingested sessions and regenerate already-persisted insights. "
        "Without this, a session/insight batch that's already there is left untouched -- safe "
        "to call repeatedly (e.g. from a cron) without redoing work or re-spending LLM credits.",
    ),
) -> None:
    """Ingest a weekend (or full season), compute substrate, generate and persist 3 insights.

    Omitting ROUND runs every completed round on the FastF1 schedule (one agent call per
    weekend). Use --dry-run to preview which rounds would run without spending API credits.
    """
    if round is not None:
        from telogify.pipeline import run_weekend as run

        started = time.monotonic()
        with console.status(f"[bold cyan]Running weekend {year} round {round}...[/bold cyan]"):
            state = run(year, round, force=force)
        elapsed = _format_elapsed(time.monotonic() - started)
        _report_insights_done(state, elapsed)
        return

    from telogify.pipeline import run_season, season_rounds

    rounds = season_rounds(year)
    if not rounds:
        _echo_no_completed_rounds(year)
        return

    if dry_run:
        _echo_dry_run_rounds(year, rounds)
        return

    console.print(f"[bold]Running season {year}[/bold]: {len(rounds)} completed round(s)...")
    summary = run_season(
        year,
        force=force,
        on_round_start=_on_round_start,
        on_round_complete=_on_round_complete,
    )
    _echo_season_final_summary(summary)


def _resolve_poll_year(year: int | None, now: datetime) -> int:
    """The season year to poll: the given year, or `now`'s UTC year if omitted. Pure so the
    default-year behavior is testable without depending on the real clock."""
    return year if year is not None else now.year


def _poll_round_window(events, now: datetime) -> list[int]:
    """Round numbers whose race date falls within [`now` - _STALE_AFTER, `now` + 3 days] --
    normally one round, occasionally two near back-to-backs. Mirrors
    analysis.schedule.completed_rounds's shape (pure, datetime-only) so it's testable offline
    against a stubbed schedule, no network."""
    from telogify.ingest.loader import _STALE_AFTER

    window_start = now - _STALE_AFTER
    window_end = now + timedelta(days=3)
    return sorted(e.round for e in events if e.round > 0 and window_start <= e.date <= window_end)


@app.command("poll")
def poll_cmd(
    year: int | None = typer.Argument(
        None,
        help="Season year; omit to use the current UTC year. A hardcoded year would go stale "
        "at the season boundary, so the Railway cron start command should always omit this.",
    ),
) -> None:
    """Cron-safe recurring trigger: ingest whatever's newly ready in the current round window.

    Intended for a fixed schedule (e.g. Railway cron every 20-30 min). Never passes --force --
    an already-ingested session or already-persisted insight batch is left untouched, so a
    repeat call within the same window is cheap and never re-spends LLM credits. Round
    selection is windowed around `now` (not "all completed rounds") so a no-op tick doesn't
    redo the analysis/candidate-mining step for every past round on every call. Wrapped in a
    hard wall-clock cap (`_PollTimeout`) so one hung FastF1 call can't silently block every
    future scheduled run -- see `_PollTimeout`'s docstring for why that cap must be a
    `BaseException` subclass."""
    from telogify.analysis.schedule import fetch_season_schedule
    from telogify.pipeline import run_weekend

    now = datetime.utcnow()
    resolved_year = _resolve_poll_year(year, now)

    events = fetch_season_schedule(resolved_year)
    if not events:
        # fetch_season_schedule swallows every failure into (), so an off-season year and a
        # persistent FastF1 outage look identical from here -- flag that explicitly rather
        # than silently reporting a healthy no-op either way.
        console.print(
            f"[yellow]Schedule fetch returned nothing for {resolved_year} "
            "(off-season, or FastF1 is unreachable -- indistinguishable from here).[/yellow]"
        )
        return

    rounds = _poll_round_window(events, now)
    if not rounds:
        console.print(
            f"[yellow]Schedule fetched for {resolved_year}; no rounds in the current window.[/yellow]"
        )
        return

    signal.signal(signal.SIGALRM, _raise_poll_timeout)
    signal.alarm(_POLL_TIMEOUT_S)
    try:
        for rnd in rounds:
            started = time.monotonic()
            console.print(f"  [cyan]→[/cyan] round [bold]{rnd}[/bold] polling...")
            state = run_weekend(resolved_year, rnd)
            elapsed = _format_elapsed(time.monotonic() - started)
            _report_insights_done(state, elapsed)
    finally:
        signal.alarm(0)


@app.command("run-insights")
def run_insights_cmd(
    year: int,
    round: int | None = typer.Argument(
        None, help="Round number; omit to regenerate insights for all completed rounds."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="List completed rounds only; do not call the agent."
    ),
    workers: int = typer.Option(
        4, "--workers", help="Rounds to regenerate in parallel. Lower if you hit LLM rate limits."
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Regenerate an insight batch even if it's already persisted. Without this, a round "
        "whose insights are already generated is left untouched -- safe to call repeatedly "
        "without re-spending LLM credits.",
    ),
) -> None:
    """Regenerate only the 3 insights from already-ingested data (LLM only, no FastF1 ingest).

    Recomputes candidates and re-runs the agent. Omitting ROUND runs every completed round on
    the schedule (rounds run in parallel across --workers threads). Use --dry-run to preview
    without API spend. Requires prior ingest via run-weekend."""
    if round is not None:
        _run_insights_one(year, round, force=force)
        return

    from telogify.pipeline import run_insights_season, season_rounds

    rounds = season_rounds(year)
    if not rounds:
        _echo_no_completed_rounds(year)
        return

    if dry_run:
        _echo_llm_model()
        _echo_dry_run_rounds(year, rounds)
        return

    _echo_llm_model()
    console.print(
        f"[bold]Regenerating insights for season {year}[/bold]: {len(rounds)} completed round(s), "
        f"{min(workers, len(rounds))} in parallel..."
    )
    summary = run_insights_season(
        year,
        max_workers=workers,
        force=force,
        on_round_start=_on_round_start_line,
        on_round_complete=_on_round_complete,
    )
    _echo_season_final_summary(summary)


@app.command("run-season-deployment")
def run_season_deployment_cmd(year: int) -> None:
    """Regenerate the season deployment section's LLM verdicts (one per power-unit
    manufacturer, ranked best to worst) from already-ingested accel samples. LLM only, no
    FastF1 ingest; needs at least 3 power-unit manufacturers with race data this year."""
    from sqlmodel import Session

    from telogify.agent.season_deployment import (
        generate_season_deployment_verdicts,
        persist_season_deployment,
    )
    from telogify.analysis.season import build_season_accel_scatter
    from telogify.db import engine

    _echo_llm_model()
    started = time.monotonic()
    with Session(engine) as db:
        scatter = build_season_accel_scatter(year, db)
        with console.status(f"[bold cyan]Writing season {year} deployment verdicts...[/bold cyan]"):
            verdicts, metrics = generate_season_deployment_verdicts(scatter)
        if not verdicts:
            console.print(f"[yellow]Not enough power-unit data for {year} yet; nothing persisted.[/yellow]")
            return
        persist_season_deployment(year, verdicts, metrics, db)
    elapsed = _format_elapsed(time.monotonic() - started)
    console.print(f"[green]Done:[/green] persisted [bold]{len(verdicts)}[/bold] verdict(s) [dim]({elapsed})[/dim].")


@app.command("ingest")
def ingest_cmd(
    year: int,
    round: int | None = typer.Argument(
        None, help="Round number; omit to ingest all completed rounds for the year."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="List completed rounds only; do not ingest."
    ),
) -> None:
    """Re-run FastF1 ingest only: no analysis, no candidates, no LLM spend.

    Rewrites every ingest extractor's tables idempotently from the FastF1 cache; use after an
    ingest extractor changes. Omitting ROUND ingests every completed round on the schedule."""
    from telogify.pipeline import run_ingest, season_rounds

    if round is not None:
        with console.status(f"[bold cyan]Ingesting {year} round {round}...[/bold cyan]"):
            run_ingest(year, round)
        console.print("[green]Done.[/green]")
        return

    rounds = season_rounds(year)
    if not rounds:
        _echo_no_completed_rounds(year)
        return

    if dry_run:
        _echo_dry_run_rounds(year, rounds)
        return

    console.print(f"[bold]Ingesting season {year}[/bold]: {len(rounds)} completed round(s)...")
    table = Table(title="Summary")
    table.add_column("Round", justify="right")
    table.add_column("Status")
    table.add_column("Time", justify="right")
    failed: list[tuple[int, str]] = []
    for i, rnd in enumerate(rounds, start=1):
        started = time.monotonic()
        status = console.status(f"[bold cyan]round {rnd} ({i}/{len(rounds)}): ingesting...[/bold cyan]")
        status.start()
        try:
            run_ingest(year, rnd)
            status.stop()
            elapsed = _format_elapsed(time.monotonic() - started)
            console.print(f"  [green]✓[/green] round [bold]{rnd}[/bold] ({i}/{len(rounds)}): ok [dim]({elapsed})[/dim]")
            table.add_row(str(rnd), "[green]OK[/green]", elapsed)
        except Exception as exc:
            status.stop()
            elapsed = _format_elapsed(time.monotonic() - started)
            console.print(
                f"  [red]✗[/red] round [bold]{rnd}[/bold] ({i}/{len(rounds)}): "
                f"[red]failed[/red] [dim]({elapsed})[/dim] - {escape(str(exc))}"
            )
            table.add_row(str(rnd), "[red]FAILED[/red]", elapsed)
            failed.append((rnd, str(exc)))

    console.print()
    console.print(table)
    if failed:
        _print_failures(failed)
        raise typer.Exit(code=1)
    console.print(f"\n[green]Done:[/green] {len(rounds)} round(s) ingested.")


@app.command("diagnose")
def diagnose(year: int, round: int) -> None:
    """Print per-constructor clean-lap counts and mean attribution confidence."""
    from sqlmodel import Session

    from telogify.analysis.diagnose import diagnose as run_diagnose
    from telogify.db import engine

    with Session(engine) as db:
        console.print(escape(run_diagnose(year, round, db)))


def _render_insight_block(
    slot: int,
    header: str,
    body: str,
    *,
    team: str | None = None,
    model_used: str | None = None,
    prompt_version: str | None = None,
) -> str:
    label = f"[bold]{escape(team)}[/bold]: " if team else ""
    provenance = (
        f"\n[dim italic]{escape(model_used or '?')} · prompt v{escape(prompt_version or '?')}[/dim italic]"
        if model_used or prompt_version
        else ""
    )
    return (
        f"[cyan]({slot})[/cyan] {label}[bold]{escape(header)}[/bold]\n"
        f"[dim]{escape(body)}[/dim]{provenance}"
    )


@app.command("list-insights")
def list_insights(
    year: int | None = typer.Argument(None, help="Omit for every weekend."),
    round: int | None = typer.Argument(None, help="Requires YEAR; omit for the whole season."),
) -> None:
    """Print all persisted insights, grouped by race weekend."""
    from sqlmodel import Session, select

    from telogify.db import engine
    from telogify.models import Insight, QualiInsight, RaceWeekend

    with Session(engine) as db:
        query = select(RaceWeekend).order_by(RaceWeekend.year, RaceWeekend.round)
        if year is not None:
            query = query.where(RaceWeekend.year == year)
        if round is not None:
            query = query.where(RaceWeekend.round == round)
        weekends = db.exec(query).all()

        if not weekends:
            console.print("[yellow]No race weekends found.[/yellow]")
            return

        for weekend in weekends:
            insights = db.exec(
                select(Insight)
                .where(Insight.weekend_id == weekend.id)
                .order_by(Insight.slot)
            ).all()
            quali_insights = db.exec(
                select(QualiInsight)
                .where(QualiInsight.weekend_id == weekend.id)
                .order_by(QualiInsight.slot)
            ).all()

            blocks: list[str] = []
            if not insights:
                blocks.append("[dim](no insights persisted)[/dim]")
            else:
                blocks.extend(
                    _render_insight_block(
                        i.slot, i.header, i.explanation_web,
                        model_used=i.model_used, prompt_version=i.prompt_version,
                    )
                    for i in insights
                )

            if quali_insights:
                blocks.append("[bold]Qualifying:[/bold]")
                blocks.extend(
                    _render_insight_block(
                        i.slot, i.header, i.explanation_web, team=i.team,
                        model_used=i.model_used, prompt_version=i.prompt_version,
                    )
                    for i in quali_insights
                )
            else:
                blocks.append("[bold]Qualifying:[/bold] [dim](none persisted)[/dim]")

            title = (
                f"{weekend.year} Round {weekend.round}: {escape(weekend.event_name)} "
                f"({escape(weekend.circuit_name)}, {escape(weekend.country)})"
            )
            console.print(Panel("\n\n".join(blocks), title=title, title_align="left", border_style="cyan"))


@app.command("send-digest")
def send_digest(year: int, round: int) -> None:
    """Email the 3 insights for a weekend via Resend."""
    from sqlmodel import Session

    from telogify.db import engine
    from telogify.email import send_digest as run_send

    with Session(engine) as db:
        sent = run_send(year, round, db)
    console.print(f"[green]Sent digest to {sent} recipient(s).[/green]")


@app.command("preview-digest")
def preview_digest(
    year: int,
    round: int,
    out: str = typer.Option("digest-preview.html", "--out", help="Path to write the rendered HTML."),
) -> None:
    """Render the email digest to a local HTML file for browser preview. No send, no API key."""
    from pathlib import Path

    from sqlmodel import Session

    from telogify.db import engine
    from telogify.email import render_digest_preview

    with Session(engine) as db:
        html_body = render_digest_preview(year, round, db)
    # Already a full standalone document (real Google Fonts need a <head>).
    Path(out).write_text(html_body)
    console.print(f"[green]Wrote preview to[/green] [cyan]{escape(out)}[/cyan]")


@app.command("emailsim-probe")
def emailsim_probe(
    kind: str = typer.Option("color", "--kind", help="Which probe to render: color | css."),
    out: str = typer.Option("probe.html", "--out", help="Path to write the rendered HTML."),
) -> None:
    """Render an emailsim probe email to a local HTML file. No send, no API key."""
    from pathlib import Path

    from telogify.emailsim.probe import render_probe_a, render_probe_b

    if kind == "color":
        html_body = render_probe_a()
    elif kind == "css":
        html_body = render_probe_b()
    else:
        raise typer.BadParameter(f"unknown probe kind {kind!r} (expected: color | css)")
    Path(out).write_text(html_body)
    console.print(f"[green]Wrote probe to[/green] [cyan]{escape(out)}[/cyan]")


@app.command("emailsim-extract")
def emailsim_extract(
    shot: str = typer.Argument(..., help="Path to a screenshot PNG."),
    kind: str = typer.Option("color", "--kind", help="Which probe this screenshot is of: color | css."),
    out: str = typer.Option("extract.json", "--out", help="Path to write the measured results as JSON."),
    debug_overlay: str = typer.Option(
        None, "--debug-overlay", help="Optional path to write an annotated overlay PNG."
    ),
    tol: int = typer.Option(40, "--tol", help="Color-distance tolerance for locating the magenta frame."),
) -> None:
    """Extract measured results from a probe screenshot. Always prints a summary so a bad
    extraction is visible immediately rather than silently trusted."""
    import json
    from pathlib import Path

    from telogify.emailsim.extract import (
        draw_debug_overlay,
        load_image,
        locate_and_classify,
        locate_and_extract,
        locate_frames,
    )
    from telogify.emailsim.probe import probe_a_grids, probe_b_grids

    image = load_image(shot)

    if kind == "color":
        grids = probe_a_grids()
        results = locate_and_extract(image, grids, tol=tol)
        payload = {
            grid_name: [
                {"row": m.row, "col": m.col, "expected_hex": m.expected_hex, "measured_hex": m.measured_hex, "delta": m.delta}
                for m in measurements
            ]
            for grid_name, measurements in results.items()
        }
        total = sum(len(v) for v in results.values())
        max_delta = max((m.delta for measurements in results.values() for m in measurements), default=0.0)
        console.print(
            f"[green]Extracted {total} swatches[/green] across {len(results)} grid(s). "
            f"Max delta from sent color: {max_delta:.1f}"
        )
    elif kind == "css":
        grids = probe_b_grids()
        results = locate_and_classify(image, grids, tol=tol)
        payload = {
            grid_name: [
                {"id": v.id, "label": v.label, "verdict": v.verdict, "measured_rgb": v.measured_rgb}
                for v in verdicts
            ]
            for grid_name, verdicts in results.items()
        }
        for verdicts in results.values():
            for v in verdicts:
                console.print(f"  [cyan]{v.id:<28}[/cyan] {v.verdict}")
        total = sum(len(v) for v in results.values())
        console.print(f"[green]Classified {total} CSS test(s).[/green]")
    else:
        raise typer.BadParameter(f"unknown probe kind {kind!r} (expected: color | css)")

    if debug_overlay:
        boxes = locate_frames(image, tol=tol)
        overlay = draw_debug_overlay(image, grids, boxes)
        overlay.save(debug_overlay)
        console.print(f"[green]Wrote debug overlay to[/green] [cyan]{escape(debug_overlay)}[/cyan]")

    Path(out).write_text(json.dumps(payload, indent=2))
    console.print(f"[green]Wrote results to[/green] [cyan]{escape(out)}[/cyan]")


@app.command("emailsim-send")
def emailsim_send(
    to: str = typer.Option(..., "--to", help="Recipient email address."),
    kind: str = typer.Option("color", "--kind", help="Which probe to send: color | css."),
) -> None:
    """Send an emailsim probe via Resend. Real send, real API key required."""
    from telogify.config import settings
    from telogify.emailsim.probe import render_probe_a, render_probe_b

    if kind == "color":
        html_body, subject = render_probe_a(), "emailsim Probe A -- color calibration"
    elif kind == "css":
        html_body, subject = render_probe_b(), "emailsim Probe B -- CSS support matrix"
    else:
        raise typer.BadParameter(f"unknown probe kind {kind!r} (expected: color | css)")

    if not settings.resend_api_key:
        raise RuntimeError("RESEND_API_KEY is not set; cannot send the probe.")

    import resend

    resend.api_key = settings.resend_api_key
    resend.Emails.send({"from": settings.resend_from, "to": [to], "subject": subject, "html": html_body})
    console.print(f"[green]Sent {kind} probe to[/green] [cyan]{escape(to)}[/cyan]")


@app.command("emailsim-render")
def emailsim_render(
    year: int,
    round: int,
    client: str = typer.Option("gmail-ios", "--client", help="Client profile family: gmail-ios."),
    theme: str = typer.Option("light", "--theme", help="light | dark."),
    out: str = typer.Option("digest-simulated.html", "--out", help="Path to write the simulated HTML."),
) -> None:
    """Render the real digest through a measured emailsim profile (color transform + CSS
    support stripping), for comparison against the current naive/emulated render. No send."""
    from pathlib import Path

    from sqlmodel import Session

    from telogify.db import engine
    from telogify.email import render_digest_preview
    from telogify.emailsim.profiles import get_profile
    from telogify.emailsim.simulate import apply

    profile = get_profile(f"{client}-{theme}")
    with Session(engine) as db:
        html_body = render_digest_preview(year, round, db)
    simulated = apply(html_body, profile)
    Path(out).write_text(simulated)
    console.print(f"[green]Wrote simulated ({profile.name}) digest to[/green] [cyan]{escape(out)}[/cyan]")


if __name__ == "__main__":
    app()
