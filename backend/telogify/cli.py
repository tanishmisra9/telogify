"""Telogify CLI. Manual triggers only (no scheduler)."""

import typer

app = typer.Typer(
    add_completion=False,
    help="Telogify: 3 quantified telemetry insights per F1 race weekend.",
)


@app.command("run-weekend")
def run_weekend(year: int, round: int) -> None:
    """Ingest a weekend, compute substrate, generate and persist 3 insights."""
    from telogify.pipeline import run_weekend as run

    typer.echo(f"Running weekend {year} round {round}...")
    state = run(year, round)
    typer.echo(f"Done: persisted {state.get('insight_count', 0)} insights.")


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
