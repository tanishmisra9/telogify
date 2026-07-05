"""Telogify CLI. Manual triggers only (no scheduler)."""

import typer

app = typer.Typer(
    add_completion=False,
    help="Telogify: 3 quantified telemetry insights per F1 race weekend.",
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

        typer.echo(f"Running weekend {year} round {round}...")
        state = run(year, round)
        typer.echo(f"Done: persisted {state.get('insight_count', 0)} insights.")
        return

    from telogify.pipeline import run_season, season_rounds

    rounds = season_rounds(year)
    if not rounds:
        typer.echo(f"No completed rounds found for {year}.")
        return

    if dry_run:
        typer.echo(f"{year} completed rounds ({len(rounds)}): {', '.join(str(r) for r in rounds)}")
        return

    typer.echo(f"Running season {year}: {len(rounds)} completed round(s)...")
    summary = run_season(year)
    total = len(summary.rounds)
    for i, result in enumerate(summary.results, start=1):
        if result.ok:
            typer.echo(
                f"  round {result.round} ({i}/{total}): ok, "
                f"{result.insight_count} insight(s) persisted"
            )
        else:
            typer.echo(f"  round {result.round} ({i}/{total}): failed - {result.error}")

    typer.echo("")
    typer.echo("Summary:")
    for result in summary.results:
        if result.ok:
            typer.echo(f"  R{result.round}: {result.insight_count} insights")
        else:
            typer.echo(f"  R{result.round}: FAILED ({result.error})")

    failed = [r for r in summary.results if not r.ok]
    if failed:
        typer.echo(f"\n{len(failed)} round(s) failed.")
        raise typer.Exit(code=1)

    typer.echo(f"\nDone: {len(summary.results)} round(s) completed.")


@app.command("regen-insights")
def regen_insights(year: int, round: int) -> None:
    """Regenerate only the 3 insights from already-ingested data: recomputes candidates and
    re-runs the agent, skipping FastF1 ingest. Use after changing scoring or prompts."""
    from telogify.pipeline import regen_insights as run

    typer.echo(f"Regenerating insights for {year} round {round}...")
    state = run(year, round)
    typer.echo(f"Done: persisted {state.get('insight_count', 0)} insights.")


@app.command("diagnose")
def diagnose(year: int, round: int) -> None:
    """Print per-constructor clean-lap counts and mean attribution confidence."""
    from sqlmodel import Session

    from telogify.analysis.diagnose import diagnose as run_diagnose
    from telogify.db import engine

    with Session(engine) as db:
        typer.echo(run_diagnose(year, round, db))


@app.command("list-insights")
def list_insights(year: int | None = None) -> None:
    """Print all persisted insights, grouped by race weekend."""
    from sqlmodel import Session, select

    from telogify.db import engine
    from telogify.models import Insight, RaceWeekend

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

            typer.echo("=" * 78)
            typer.echo(
                f"{weekend.year} Round {weekend.round}: {weekend.event_name} "
                f"({weekend.circuit_name}, {weekend.country})"
            )
            typer.echo("=" * 78)

            if not insights:
                typer.echo("  (no insights persisted)\n")
                continue

            for insight in insights:
                typer.echo(f"\n[{insight.slot}] {insight.header}")
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
    typer.echo(f"Sent digest to {sent} recipient(s).")


if __name__ == "__main__":
    app()
