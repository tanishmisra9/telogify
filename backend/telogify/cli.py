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


@app.command("diagnose")
def diagnose(year: int, round: int) -> None:
    """Print per-constructor clean-lap counts and mean attribution confidence."""
    from sqlmodel import Session

    from telogify.analysis.diagnose import diagnose as run_diagnose
    from telogify.db import engine

    with Session(engine) as db:
        typer.echo(run_diagnose(year, round, db))


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
