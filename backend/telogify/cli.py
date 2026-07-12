"""Telogify CLI. Manual triggers only (no scheduler)."""

import sys

import typer

from telogify.pipeline import RoundResult

app = typer.Typer(
    add_completion=False,
    help="Telogify: 3 quantified telemetry insights per F1 race weekend.",
)


def _progress(msg: str) -> None:
    typer.echo(msg)
    sys.stdout.flush()


def _on_round_start(round: int, index: int, total: int) -> None:
    _progress(f"  round {round} ({index}/{total}): running...")


def _on_round_complete(result: RoundResult, index: int, total: int) -> None:
    if result.ok:
        _progress(
            f"  round {result.round} ({index}/{total}): ok, "
            f"{result.insight_count} insight(s) persisted"
        )
    else:
        _progress(f"  round {result.round} ({index}/{total}): failed - {result.error}")


def _echo_llm_model() -> None:
    from telogify.config import configured_llm_label

    _progress(f"Model: {configured_llm_label()}")


def _echo_season_final_summary(summary) -> None:
    """Aggregate summary after all rounds have been logged live."""
    _progress("")
    _progress("Summary:")
    for result in summary.results:
        if result.ok:
            _progress(f"  R{result.round}: {result.insight_count} insights")
        else:
            _progress(f"  R{result.round}: FAILED ({result.error})")

    failed = [r for r in summary.results if not r.ok]
    if failed:
        _progress(f"\n{len(failed)} round(s) failed.")
        raise typer.Exit(code=1)

    _progress(f"\nDone: {len(summary.results)} round(s) completed.")


def _run_insights_one(year: int, round: int) -> None:
    from telogify.pipeline import regen_insights

    _echo_llm_model()
    _progress(f"Regenerating insights for {year} round {round}...")
    state = regen_insights(year, round)
    _progress(f"Done: persisted {state.get('insight_count', 0)} insights.")


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
        state = run(year, round)
        _progress(f"Done: persisted {state.get('insight_count', 0)} insights.")
        return

    from telogify.pipeline import run_season, season_rounds

    rounds = season_rounds(year)
    if not rounds:
        _progress(f"No completed rounds found for {year}.")
        return

    if dry_run:
        _progress(f"{year} completed rounds ({len(rounds)}): {', '.join(str(r) for r in rounds)}")
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
        _progress(f"No completed rounds found for {year}.")
        return

    if dry_run:
        _echo_llm_model()
        _progress(f"{year} completed rounds ({len(rounds)}): {', '.join(str(r) for r in rounds)}")
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
        _progress(f"No completed rounds found for {year}.")
        return

    if dry_run:
        _progress(f"{year} completed rounds ({len(rounds)}): {', '.join(str(r) for r in rounds)}")
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
