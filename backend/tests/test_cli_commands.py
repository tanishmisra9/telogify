"""CLI commands that had no test: the season-deployment and race-start commands, the preview /
emailsim tooling, and the send-digest branches that must NOT send. Every pipeline, LLM and mail
call is stubbed; nothing here reaches FastF1, an LLM, or Resend."""

import types
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlmodel import Session, select
from test_cli import plain
from typer.testing import CliRunner

from telogify import cli
from telogify.analysis.race_start import Skip
from telogify.analysis.schedule import Event
from telogify.models import Insight, RaceWeekend, Subscriber

runner = CliRunner()


def _invoke(*args, **kw):
    return runner.invoke(cli.app, list(args), **kw)


# --- small helpers ---------------------------------------------------------------------------------

def test_format_elapsed_switches_to_minutes():
    assert cli._format_elapsed(5.04) == "5.0s"
    assert cli._format_elapsed(125.5) == "2m 5.5s"


# --- run-season-deployment -------------------------------------------------------------------------

def _stub_season_deployment(monkeypatch, test_engine, verdicts):
    persisted = []
    monkeypatch.setattr("telogify.db.engine", test_engine)
    monkeypatch.setattr(cli, "_echo_llm_model", lambda: None)
    monkeypatch.setattr("telogify.analysis.season.build_season_accel_scatter", lambda year, db: {"x": []})
    monkeypatch.setattr(
        "telogify.agent.season_deployment.generate_season_deployment_verdicts",
        lambda scatter: (verdicts, [{"pu": "A"}] if verdicts else []),
    )
    monkeypatch.setattr(
        "telogify.agent.season_deployment.persist_season_deployment",
        lambda year, v, m, db: persisted.append((year, v, m)),
    )
    return persisted


def test_run_season_deployment_persists_verdicts(monkeypatch, test_engine):
    persisted = _stub_season_deployment(monkeypatch, test_engine, [{"pu": "A"}, {"pu": "B"}, {"pu": "C"}])
    result = _invoke("run-season-deployment", "2026")
    assert result.exit_code == 0
    assert "persisted 3 verdict(s)" in plain(result.output)
    assert [p[0] for p in persisted] == [2026]


def test_run_season_deployment_without_enough_data_persists_nothing(monkeypatch, test_engine):
    persisted = _stub_season_deployment(monkeypatch, test_engine, [])
    result = _invoke("run-season-deployment", "2026")
    assert result.exit_code == 0
    assert "Not enough power-unit data" in plain(result.output)
    assert persisted == []


# --- refresh-race-start / refresh-results / run-insights --------------------------------------------

def test_refresh_race_start_with_no_usable_data_writes_nothing(monkeypatch):
    monkeypatch.setattr("telogify.pipeline.run_refresh_race_start", lambda y, r, dry_run=False: None)
    result = _invoke("refresh-race-start", "2026", "5")
    assert result.exit_code == 0
    assert "nothing written" in plain(result.output)


def test_refresh_race_start_lists_times_and_groups_unlisted_drivers_by_reason(monkeypatch):
    found = {
        "VER": {"t_0_100_s": 2.5, "t_0_200_s": 5.0, "v_75m_kmh": 140.0},
        "HAM": {"t_0_100_s": 2.4, "t_0_200_s": None, "v_75m_kmh": None},
    }
    skipped = {"ALO": (None, Skip.TOO_SLOW), "STR": (None, Skip.TOO_SLOW), "LEC": (None, Skip.NO_DATA)}
    monkeypatch.setattr("telogify.pipeline.run_refresh_race_start", lambda y, r, dry_run=False: (found, skipped))
    out = plain(_invoke("refresh-race-start", "2026", "5", "--dry-run").output)
    assert "VER" in out and "5.00s" in out and "140 km/h" in out
    ham = next(line for line in out.splitlines() if "HAM" in line)
    assert "None" not in ham and "nan" not in ham.lower()  # a missing 0-200 renders as a dash
    assert "ALO, STR" in out  # one line per reason, drivers sorted
    assert "2 drivers would be written, 3 not listed" in out


def test_refresh_race_start_reports_written_when_not_a_dry_run(monkeypatch):
    found = {"VER": {"t_0_100_s": 2.5, "t_0_200_s": 5.0, "v_75m_kmh": 140.0}}
    monkeypatch.setattr("telogify.pipeline.run_refresh_race_start", lambda y, r, dry_run=False: (found, {}))
    assert "1 drivers written, 0 not listed" in plain(_invoke("refresh-race-start", "2026", "5").output)


def test_refresh_results_with_no_ingested_race_says_so(monkeypatch):
    monkeypatch.setattr("telogify.pipeline.run_refresh_results", lambda y, r, dry_run=False: [])
    assert "No ingested race-like session" in plain(_invoke("refresh-results", "2026", "5").output)


def test_run_insights_for_a_season_with_no_completed_rounds(monkeypatch):
    monkeypatch.setattr("telogify.pipeline.season_rounds", lambda year: [])

    def must_not_run(*a, **k):
        raise AssertionError("no rounds means no pipeline work")

    monkeypatch.setattr("telogify.pipeline.run_insights_season", must_not_run)
    result = _invoke("run-insights", "2026")
    assert result.exit_code == 0
    assert "No completed rounds found for 2026" in plain(result.output)


# --- diagnose / preview-* ---------------------------------------------------------------------------

def test_diagnose_prints_the_report_with_brackets_escaped(monkeypatch, test_engine):
    monkeypatch.setattr("telogify.db.engine", test_engine)
    monkeypatch.setattr("telogify.analysis.diagnose.diagnose", lambda y, r, db: "ranking [bold] ok")
    out = plain(_invoke("diagnose", "2026", "5").output)
    assert "ranking [bold] ok" in out


@pytest.mark.parametrize("kind", ["verify", "welcome"])
def test_preview_optin_email_writes_the_rendered_html(tmp_path, kind):
    out = tmp_path / f"{kind}.html"
    result = _invoke("preview-optin-email", kind, "--out", str(out))
    assert result.exit_code == 0
    assert "<html" in out.read_text().lower()


def test_preview_optin_email_rejects_an_unknown_kind(tmp_path):
    out = tmp_path / "x.html"
    result = _invoke("preview-optin-email", "bogus", "--out", str(out))
    assert result.exit_code == 1
    assert not out.exists()


def test_preview_digest_writes_the_html(monkeypatch, test_engine, tmp_path):
    monkeypatch.setattr("telogify.db.engine", test_engine)
    monkeypatch.setattr("telogify.email.render_digest_preview", lambda y, r, db: "<html>digest</html>")
    out = tmp_path / "d.html"
    assert _invoke("preview-digest", "2026", "5", "--out", str(out)).exit_code == 0
    assert out.read_text() == "<html>digest</html>"


def test_emailsim_render_applies_the_profile(monkeypatch, test_engine, tmp_path):
    monkeypatch.setattr("telogify.db.engine", test_engine)
    monkeypatch.setattr("telogify.email.render_digest_preview", lambda y, r, db: "<html>digest</html>")
    monkeypatch.setattr("telogify.emailsim.simulate.apply", lambda html, profile: "SIMULATED " + html)
    out = tmp_path / "s.html"
    result = _invoke("emailsim-render", "2026", "5", "--out", str(out))
    assert result.exit_code == 0
    assert out.read_text() == "SIMULATED <html>digest</html>"
    assert "Screenshot at" in plain(result.output)  # the calibrated viewport is called out


# --- emailsim-probe / -extract / -send -------------------------------------------------------------

@pytest.mark.parametrize("kind", ["color", "css", "image"])
def test_emailsim_probe_renders_each_kind(tmp_path, kind):
    out = tmp_path / "p.html"
    assert _invoke("emailsim-probe", "--kind", kind, "--out", str(out)).exit_code == 0
    assert out.read_text().strip()


def test_emailsim_probe_rejects_an_unknown_kind(tmp_path):
    assert _invoke("emailsim-probe", "--kind", "nope", "--out", str(tmp_path / "p.html")).exit_code != 0


def _measure():
    return types.SimpleNamespace(row=0, col=0, expected_hex="#ff0000", measured_hex="#fe0000", delta=1.5)


def _stub_extract(monkeypatch):
    monkeypatch.setattr("telogify.emailsim.extract.load_image", lambda path: "IMG")
    monkeypatch.setattr("telogify.emailsim.extract.locate_and_extract", lambda image, grids, tol: {"g1": [_measure()]})
    monkeypatch.setattr(
        "telogify.emailsim.extract.locate_and_classify",
        lambda image, grids, tol: {
            "g2": [types.SimpleNamespace(id="rotate", label="rotate", verdict="unsupported", measured_rgb=[1, 2, 3])]
        },
    )
    monkeypatch.setattr("telogify.emailsim.extract.locate_frames", lambda image, tol: [])
    overlay = types.SimpleNamespace(save=lambda path: Path(path).write_text("png"))
    monkeypatch.setattr("telogify.emailsim.extract.draw_debug_overlay", lambda image, grids, boxes: overlay)


@pytest.mark.parametrize("kind,needle", [("color", "Extracted 1 swatches"), ("image", "sent #ff0000"), ("css", "Classified 1 CSS")])
def test_emailsim_extract_summarises_each_kind(monkeypatch, tmp_path, kind, needle):
    _stub_extract(monkeypatch)
    out = tmp_path / "r.json"
    result = _invoke("emailsim-extract", str(tmp_path / "shot.png"), "--kind", kind, "--out", str(out))
    assert result.exit_code == 0, result.output
    assert needle in plain(result.output)
    assert out.read_text().strip().startswith("{")


def test_emailsim_extract_writes_the_debug_overlay_and_rejects_unknown_kinds(monkeypatch, tmp_path):
    _stub_extract(monkeypatch)
    overlay = tmp_path / "o.png"
    ok = _invoke(
        "emailsim-extract", str(tmp_path / "s.png"), "--kind", "color",
        "--out", str(tmp_path / "r.json"), "--debug-overlay", str(overlay),
    )
    assert ok.exit_code == 0 and overlay.read_text() == "png"
    bad = _invoke("emailsim-extract", str(tmp_path / "s.png"), "--kind", "nope", "--out", str(tmp_path / "r2.json"))
    assert bad.exit_code != 0


def test_emailsim_send_refuses_without_an_api_key():
    """conftest blanks the key, so this proves the guard, and that no send is attempted."""
    result = _invoke("emailsim-send", "--to", "me@example.com", "--kind", "color")
    assert isinstance(result.exception, RuntimeError)
    assert "RESEND_API_KEY is not set" in str(result.exception)


@pytest.mark.parametrize("kind", ["color", "css", "image"])
def test_emailsim_send_hands_the_probe_to_resend_only_when_a_key_is_set(monkeypatch, kind):
    import resend

    sent = []
    monkeypatch.setattr("telogify.config.settings.resend_api_key", "re_test_not_real")
    monkeypatch.setattr(resend, "api_key", None, raising=False)  # restored on teardown
    monkeypatch.setattr(resend.Emails, "send", staticmethod(lambda payload: sent.append(payload)))
    result = _invoke("emailsim-send", "--to", "me@example.com", "--kind", kind)
    assert result.exit_code == 0
    assert [p["to"] for p in sent] == [["me@example.com"]]


def test_emailsim_send_rejects_an_unknown_kind_before_touching_resend():
    assert _invoke("emailsim-send", "--to", "me@example.com", "--kind", "nope").exit_code != 0


# --- send-digest: the branches that must not send ----------------------------------------------------

def _seed_weekend(test_engine, *, subscribers=0):
    with Session(test_engine) as db:
        from telogify.db import set_service_scope

        set_service_scope(db)
        db.add(RaceWeekend(year=2026, round=8, circuit_name="X", country="Y", event_name="Z GP"))
        for i in range(subscribers):
            db.add(Subscriber(email=f"s{i}@example.com", status="confirmed"))
        db.commit()


def _recording_send(monkeypatch):
    calls = []
    monkeypatch.setattr("telogify.email.send_digest", lambda year, round, db: calls.append(1) or 1)
    return calls


def _marker(test_engine):
    with Session(test_engine) as db:
        return db.exec(select(RaceWeekend)).one().digest_sent_at


def test_send_digest_with_no_confirmed_subscribers_sends_nothing(monkeypatch, test_engine):
    monkeypatch.setattr("telogify.db.engine", test_engine)
    _seed_weekend(test_engine, subscribers=0)
    calls = _recording_send(monkeypatch)
    result = _invoke("send-digest", "2026", "8", "--to-subscribers")
    assert "No confirmed subscribers" in plain(result.output)
    assert calls == [] and _marker(test_engine) is None


def test_send_digest_dry_run_lists_recipients_and_sends_nothing(monkeypatch, test_engine):
    monkeypatch.setattr("telogify.db.engine", test_engine)
    _seed_weekend(test_engine, subscribers=2)
    calls = _recording_send(monkeypatch)
    result = _invoke("send-digest", "2026", "8", "--dry-run")
    out = plain(result.output)
    assert "2 confirmed subscriber(s)" in out and "Dry run: nothing sent" in out
    assert calls == [] and _marker(test_engine) is None


def test_send_digest_declined_confirmation_sends_nothing_and_claims_nothing(monkeypatch, test_engine):
    monkeypatch.setattr("telogify.db.engine", test_engine)
    _seed_weekend(test_engine, subscribers=1)
    calls = _recording_send(monkeypatch)
    result = _invoke("send-digest", "2026", "8", "--to-subscribers", input="n\n")
    assert "Aborted" in plain(result.output)
    assert calls == [] and _marker(test_engine) is None


def test_send_digest_already_sent_needs_a_second_yes(monkeypatch, test_engine):
    monkeypatch.setattr("telogify.db.engine", test_engine)
    _seed_weekend(test_engine, subscribers=1)
    with Session(test_engine) as db:
        wk = db.exec(select(RaceWeekend)).one()
        wk.digest_sent_at = datetime.utcnow()
        db.add(wk)
        db.commit()
    calls = _recording_send(monkeypatch)
    declined = _invoke("send-digest", "2026", "8", "--to-subscribers", input="y\nn\n")
    assert "already sent" in plain(declined.output) and calls == []
    confirmed = _invoke("send-digest", "2026", "8", "--to-subscribers", input="y\ny\n")
    assert confirmed.exit_code == 0 and calls == [1]


# --- poll: losing the claim race --------------------------------------------------------------------

def test_poll_does_not_send_when_another_process_claimed_the_digest_first(monkeypatch, test_engine):
    """The marker looks unset when poll reads it, but the atomic claim fails (a concurrent poll or
    a manual send-digest won). Poll must back off without sending."""
    monkeypatch.setattr("telogify.db.engine", test_engine)
    with Session(test_engine) as db:
        wk = RaceWeekend(year=2026, round=8, circuit_name="X", country="Y", event_name="Z GP")
        db.add(wk)
        db.commit()
        db.refresh(wk)
        db.add(Insight(weekend_id=wk.id, slot=1, header="h", explanation_web="w", explanation_email="e",
                       source_tool_calls_json=[]))
        db.commit()
        weekend_id = wk.id

    ready = (Event(round=8, name="Ready GP", date=datetime.utcnow() - timedelta(hours=1)),)
    monkeypatch.setattr("telogify.analysis.schedule.fetch_season_schedule", lambda year: ready)
    monkeypatch.setattr(
        "telogify.pipeline.run_weekend", lambda y, r: {"session_types": ["R"], "weekend_id": weekend_id}
    )
    monkeypatch.setattr(cli, "_claim_digest", lambda db, weekend_id: False)
    calls = _recording_send(monkeypatch)

    assert _invoke("poll", "2026").exit_code == 0
    assert calls == []
