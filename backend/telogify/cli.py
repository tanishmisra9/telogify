"""Telogify CLI. Manual triggers only (no scheduler)."""

import typer

app = typer.Typer(
    add_completion=False,
    help="Telogify: 3 quantified telemetry insights per F1 race weekend.",
)


@app.command("run-weekend")
def run_weekend(year: int, round: int) -> None:
    """Ingest a weekend, compute substrate, generate and persist 3 insights."""
    # ponytail: stub until M14 wires the pipeline.
    raise typer.Exit(_todo("run-weekend", year, round))


@app.command("diagnose")
def diagnose(year: int, round: int) -> None:
    """Print per-constructor clean-lap counts and mean attribution confidence."""
    # ponytail: stub until M9.
    raise typer.Exit(_todo("diagnose", year, round))


@app.command("send-digest")
def send_digest(year: int, round: int) -> None:
    """Email the 3 insights for a weekend via Resend."""
    # ponytail: stub until M20.
    raise typer.Exit(_todo("send-digest", year, round))


def _todo(cmd: str, year: int, round: int) -> int:
    typer.echo(f"{cmd} {year} {round}: not yet implemented")
    return 1


if __name__ == "__main__":
    app()
