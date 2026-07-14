"""Telogify CLI. Manual triggers only (no scheduler)."""

import sys
import time

import typer
from rich.console import Console
from rich.markup import escape

from telogify.pipeline import RoundResult

app = typer.Typer(
    add_completion=False,
    help="Telogify: 3 quantified telemetry insights per F1 race weekend.",
)
console = Console(highlight=False)


def _progress(msg: str) -> None:
    typer.echo(msg)
    sys.stdout.flush()


def _format_elapsed(seconds: float) -> str:
    if seconds >= 60:
        minutes, rest = divmod(seconds, 60)
        return f"{int(minutes)}m {rest:.1f}s"
    return f"{seconds:.1f}s"


# Keyed by round number: single-threaded, sequential season loop, so this is safe.
_round_start_times: dict[int, float] = {}
_round_elapsed: dict[int, str] = {}


def _on_round_start(round: int, index: int, total: int) -> None:
    _round_start_times[round] = time.monotonic()
    _progress(f"  round {round} ({index}/{total}): running...")


def _on_round_complete(result: RoundResult, index: int, total: int) -> None:
    started = _round_start_times.pop(result.round, None)
    elapsed = _format_elapsed(time.monotonic() - started) if started is not None else "?"
    _round_elapsed[result.round] = elapsed
    if result.ok:
        _progress(
            f"  round {result.round} ({index}/{total}): ok, "
            f"{result.insight_count} insight(s), "
            f"{result.quali_insight_count} qualifying insight(s) persisted ({elapsed})"
        )
    else:
        _progress(f"  round {result.round} ({index}/{total}): failed ({elapsed}) - {result.error}")


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
    """Aggregate summary after all rounds have been logged live."""
    _progress("")
    _progress("Summary:")
    for result in summary.results:
        elapsed = _round_elapsed.pop(result.round, "?")
        if result.ok:
            _progress(
                f"  R{result.round}: {result.insight_count} insights, "
                f"{result.quali_insight_count} qualifying insights ({elapsed})"
            )
        else:
            _progress(f"  R{result.round}: FAILED ({elapsed}) - {result.error}")

    failed = [r for r in summary.results if not r.ok]
    if failed:
        _progress(f"\n{len(failed)} round(s) failed.")
        raise typer.Exit(code=1)

    _progress(f"\nDone: {len(summary.results)} round(s) completed.")


def _run_insights_one(year: int, round: int) -> None:
    from telogify.pipeline import regen_insights

    _echo_llm_model()
    _progress(f"Regenerating insights for {year} round {round}...")
    started = time.monotonic()
    state = regen_insights(year, round)
    elapsed = _format_elapsed(time.monotonic() - started)
    _progress(
        f"Done: persisted {state.get('insight_count', 0)} insights, "
        f"{state.get('quali_insight_count', 0)} qualifying insights ({elapsed})."
    )


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

        _progress(f"Running weekend {year} round {round}...")
        started = time.monotonic()
        state = run(year, round)
        elapsed = _format_elapsed(time.monotonic() - started)
        _progress(
            f"Done: persisted {state.get('insight_count', 0)} insights, "
            f"{state.get('quali_insight_count', 0)} qualifying insights ({elapsed})."
        )
        return

    from telogify.pipeline import run_season, season_rounds

    rounds = season_rounds(year)
    if not rounds:
        _echo_no_completed_rounds(year)
        return

    if dry_run:
        _echo_dry_run_rounds(year, rounds)
        return

    _progress(f"Running season {year}: {len(rounds)} completed round(s)...")
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
) -> None:
    """Regenerate only the 3 insights from already-ingested data (LLM only, no FastF1 ingest).

    Recomputes candidates and re-runs the agent. Omitting ROUND runs every completed round on
    the schedule (one agent call per weekend). Use --dry-run to preview without API spend.
    Requires prior ingest via run-weekend."""
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
    _progress(f"Regenerating insights for season {year}: {len(rounds)} completed round(s)...")
    summary = run_insights_season(
        year,
        on_round_start=_on_round_start,
        on_round_complete=_on_round_complete,
    )
    _echo_season_final_summary(summary)


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
        _progress(f"Ingesting {year} round {round}...")
        run_ingest(year, round)
        _progress("Done.")
        return

    rounds = season_rounds(year)
    if not rounds:
        _echo_no_completed_rounds(year)
        return

    if dry_run:
        _echo_dry_run_rounds(year, rounds)
        return

    _progress(f"Ingesting season {year}: {len(rounds)} completed round(s)...")
    failures = 0
    for i, rnd in enumerate(rounds, start=1):
        _progress(f"  round {rnd} ({i}/{len(rounds)}): ingesting...")
        try:
            run_ingest(year, rnd)
            _progress(f"  round {rnd} ({i}/{len(rounds)}): ok")
        except Exception as exc:
            failures += 1
            _progress(f"  round {rnd} ({i}/{len(rounds)}): failed - {exc}")
    if failures:
        _progress(f"\n{failures} round(s) failed.")
        raise typer.Exit(code=1)
    _progress(f"\nDone: {len(rounds)} round(s) ingested.")


@app.command("diagnose")
def diagnose(year: int, round: int) -> None:
    """Print per-constructor clean-lap counts and mean attribution confidence."""
    from sqlmodel import Session

    from telogify.analysis.diagnose import diagnose as run_diagnose
    from telogify.db import engine

    with Session(engine) as db:
        console.print(escape(run_diagnose(year, round, db)))


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
            typer.echo("No race weekends found.")
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

            typer.echo("=" * 78)
            typer.echo(
                f"{weekend.year} Round {weekend.round}: {weekend.event_name} "
                f"({weekend.circuit_name}, {weekend.country})"
            )
            typer.echo("=" * 78)

            if not insights:
                typer.echo("  (no insights persisted)\n")
            else:
                for insight in insights:
                    typer.echo(f"\n[{insight.slot}] {insight.header}")
                    typer.echo("-" * 78)
                    typer.echo(insight.explanation_web)
                typer.echo("")

            if not quali_insights:
                typer.echo("  (no qualifying insights persisted)\n")
                continue

            typer.echo("Qualifying:")
            for insight in quali_insights:
                typer.echo(f"\n[{insight.slot}] {insight.team}: {insight.header}")
                typer.echo("-" * 78)
                typer.echo(insight.explanation_web)
            typer.echo("")


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
