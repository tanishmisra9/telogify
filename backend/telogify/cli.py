"""Telogify CLI. Manual triggers only (no scheduler)."""

import logging
import time

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
    console.print(
        f"[green]Done:[/green] persisted [bold]{state.get('insight_count', 0)}[/bold] insights, "
        f"[bold]{state.get('quali_insight_count', 0)}[/bold] qualifying insights [dim]({elapsed})[/dim]."
    )


def _run_insights_one(year: int, round: int) -> None:
    from telogify.pipeline import regen_insights

    _echo_llm_model()
    started = time.monotonic()
    with console.status(f"[bold cyan]Regenerating insights for {year} round {round}...[/bold cyan]"):
        state = regen_insights(year, round)
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
) -> None:
    """Ingest a weekend (or full season), compute substrate, generate and persist 3 insights.

    Omitting ROUND runs every completed round on the FastF1 schedule (one agent call per
    weekend). Use --dry-run to preview which rounds would run without spending API credits.
    """
    if round is not None:
        from telogify.pipeline import run_weekend as run

        started = time.monotonic()
        with console.status(f"[bold cyan]Running weekend {year} round {round}...[/bold cyan]"):
            state = run(year, round)
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
        on_round_start=_on_round_start,
        on_round_complete=_on_round_complete,
    )
    _echo_season_final_summary(summary)


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
) -> None:
    """Regenerate only the 3 insights from already-ingested data (LLM only, no FastF1 ingest).

    Recomputes candidates and re-runs the agent. Omitting ROUND runs every completed round on
    the schedule (rounds run in parallel across --workers threads). Use --dry-run to preview
    without API spend. Requires prior ingest via run-weekend."""
    if round is not None:
        _run_insights_one(year, round)
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


def _render_insight_block(slot: int, header: str, body: str, *, team: str | None = None) -> str:
    label = f"[bold]{escape(team)}[/bold]: " if team else ""
    return (
        f"[cyan]({slot})[/cyan] {label}[bold]{escape(header)}[/bold]\n"
        f"[dim]{escape(body)}[/dim]"
    )


@app.command("list-insights")
def list_insights(year: int | None = None) -> None:
    """Print all persisted insights, grouped by race weekend."""
    from sqlmodel import Session, select

    from telogify.db import engine
    from telogify.models import Insight, QualiInsight, RaceWeekend

    with Session(engine) as db:
        query = select(RaceWeekend).order_by(RaceWeekend.year, RaceWeekend.round)
        if year is not None:
            query = query.where(RaceWeekend.year == year)
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
                    _render_insight_block(i.slot, i.header, i.explanation_web) for i in insights
                )

            if quali_insights:
                blocks.append("[bold]Qualifying:[/bold]")
                blocks.extend(
                    _render_insight_block(i.slot, i.header, i.explanation_web, team=i.team)
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
    # Wrap in a minimal standards-mode shell for browser preview only (real sends stay a bare
    # fragment; without a doctype, browsers render file:// fragments in quirks mode, which
    # breaks the box model and causes horizontal overflow that doesn't happen in an inbox).
    page = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'></head>"
        f"<body style='margin:0'>{html_body}</body></html>"
    )
    Path(out).write_text(page)
    console.print(f"[green]Wrote preview to[/green] [cyan]{escape(out)}[/cyan]")


if __name__ == "__main__":
    app()
