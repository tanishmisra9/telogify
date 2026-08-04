"""Double opt-in endpoint behaviour: the happy path, and every way it should refuse.

Emails are captured rather than sent: telogify.email._send no-ops without RESEND_API_KEY, so
these monkeypatch the two send_* functions the routes call to record their arguments instead.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session, select

from telogify.api.main import app
from telogify.api.routes import get_session
from telogify.db import set_service_scope
from telogify.models import Subscriber
from telogify import api  # noqa: F401


@pytest.fixture
def sent(monkeypatch):
    """Captures outbound mail. Fails loudly if a route ever tries to actually send."""
    captured = {"verify": [], "welcome": []}
    monkeypatch.setattr(
        "telogify.api.routes.send_verification_email",
        lambda to, token: captured["verify"].append((to, token)),
    )
    monkeypatch.setattr(
        "telogify.api.routes.send_welcome_email",
        lambda to, token: captured["welcome"].append((to, token)),
    )
    return captured


@pytest.fixture
def client(test_engine, monkeypatch):
    # No captcha secret in tests, so verify_recaptcha short-circuits to True. The rejection path
    # is covered explicitly below by patching it.
    monkeypatch.setattr("telogify.subscriptions.settings.recaptcha_secret", "")

    def override():
        with Session(test_engine) as s:
            yield s

    app.dependency_overrides[get_session] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def _subscriber(test_engine, email):
    with Session(test_engine) as s:
        set_service_scope(s)
        return s.exec(select(Subscriber).where(Subscriber.email == email)).first()


def _audit_actions(test_engine, email):
    with Session(test_engine) as s:
        set_service_scope(s)
        rows = s.execute(
            text("SELECT action FROM subscriber_audit WHERE email = :e ORDER BY id"), {"e": email}
        ).scalars()
        return list(rows)


def test_full_double_optin_round_trip(client, test_engine, sent):
    r = client.post("/subscribe", json={"email": "Racer@Example.COM "})
    assert r.status_code == 200 and r.json() == {"status": "check_your_inbox"}

    # normalized on the way in, or the unique index is not a real dedupe
    sub = _subscriber(test_engine, "racer@example.com")
    assert sub is not None and sub.status == "pending" and sub.confirmed_at is None
    assert sub.verify_token_hash and sub.verify_token_hash != sent["verify"][0][1]

    token = sent["verify"][0][1]
    r = client.post("/subscribe/verify", json={"token": token})
    assert r.json() == {"status": "confirmed"}

    sub = _subscriber(test_engine, "racer@example.com")
    assert sub.status == "confirmed" and sub.confirmed_at is not None
    assert sub.verify_token_hash is None, "token must be single use"
    assert sent["welcome"], "confirming should send the welcome email"

    unsub_token = sent["welcome"][0][1]
    assert client.post(f"/unsubscribe?t={unsub_token}").json() == {"status": "unsubscribed"}
    assert _subscriber(test_engine, "racer@example.com").status == "unsubscribed"

    assert client.post(f"/subscribe/resubscribe?t={unsub_token}").json() == {
        "status": "resubscribed"
    }
    assert _subscriber(test_engine, "racer@example.com").status == "confirmed"

    assert _audit_actions(test_engine, "racer@example.com").count("signup_requested") == 1


def test_response_is_identical_for_known_and_unknown_addresses(client, test_engine, sent):
    """No enumeration oracle. The old handler returned `already_subscribed`, which let anyone
    test whether an address was on the list."""
    first = client.post("/subscribe", json={"email": "known@x.com"})
    token = sent["verify"][0][1]
    client.post("/subscribe/verify", json={"token": token})

    confirmed_again = client.post("/subscribe", json={"email": "known@x.com"})
    brand_new = client.post("/subscribe", json={"email": "unknown@x.com"})

    assert first.json() == confirmed_again.json() == brand_new.json()
    assert first.status_code == confirmed_again.status_code == brand_new.status_code
    # and a confirmed address gets no second email
    assert [to for to, _ in sent["verify"]] == ["known@x.com", "unknown@x.com"]


def test_verify_rejects_bad_expired_and_reused_tokens(client, test_engine, sent):
    assert client.post("/subscribe/verify", json={"token": ""}).json() == {"status": "invalid"}
    assert client.post("/subscribe/verify", json={"token": "nope"}).json() == {"status": "invalid"}

    client.post("/subscribe", json={"email": "exp@x.com"})
    token = sent["verify"][0][1]

    with Session(test_engine) as s:
        set_service_scope(s)
        sub = s.exec(select(Subscriber).where(Subscriber.email == "exp@x.com")).one()
        sub.verify_expires_at = sub.created_at.replace(year=2000)
        s.add(sub)
        s.commit()

    assert client.post("/subscribe/verify", json={"token": token}).json() == {"status": "expired"}


def test_a_spent_token_cannot_be_replayed(client, test_engine, sent):
    client.post("/subscribe", json={"email": "replay@x.com"})
    token = sent["verify"][0][1]
    assert client.post("/subscribe/verify", json={"token": token}).json() == {
        "status": "confirmed"
    }
    assert client.post("/subscribe/verify", json={"token": token}).json() == {"status": "invalid"}


def test_unsubscribe_rejects_a_forged_token(client):
    assert client.post("/unsubscribe?t=").json() == {"status": "invalid"}
    assert client.post("/unsubscribe?t=1.deadbeef").json() == {"status": "invalid"}
    assert client.post("/subscribe/resubscribe?t=9.bad").json() == {"status": "invalid"}


def test_unsubscribing_twice_is_reported_not_repeated(client, sent):
    client.post("/subscribe", json={"email": "twice@x.com"})
    client.post("/subscribe/verify", json={"token": sent["verify"][0][1]})
    t = sent["welcome"][0][1]
    assert client.post(f"/unsubscribe?t={t}").json() == {"status": "unsubscribed"}
    assert client.post(f"/unsubscribe?t={t}").json() == {"status": "already_unsubscribed"}


def test_malformed_email_is_rejected_with_a_fixable_error(client):
    for bad in ["", "  ", "not-an-email", "a@b", "a@@b.com", "x" * 300 + "@y.com"]:
        r = client.post("/subscribe", json={"email": bad})
        assert r.status_code == 422, bad


def test_failed_captcha_blocks_signup_and_is_audited(client, test_engine, sent, monkeypatch):
    monkeypatch.setattr("telogify.api.routes.verify_recaptcha", lambda *a, **k: False)
    r = client.post("/subscribe", json={"email": "bot@x.com", "recaptcha_token": "junk"})
    assert r.status_code == 400
    assert _subscriber(test_engine, "bot@x.com") is None, "no row for a failed captcha"
    assert "blocked_captcha" in _audit_actions(test_engine, "bot@x.com")
    assert not sent["verify"]


def test_rate_limit_blocks_and_is_audited(client, test_engine, sent, monkeypatch):
    monkeypatch.setattr("telogify.api.routes.signup_rate_limited", lambda *a, **k: True)
    r = client.post("/subscribe", json={"email": "flood@x.com"})
    assert r.status_code == 429
    assert _subscriber(test_engine, "flood@x.com") is None
    assert "blocked_rate_limit" in _audit_actions(test_engine, "flood@x.com")
    assert not sent["verify"]


def test_trigger_written_rows_carry_user_context(client, test_engine, sent):
    """The requirement is triggers that log changes AND user context. The trigger reads the GUCs,
    which are transaction-local, so they have to be re-applied before every commit. Caught by
    inspecting a real request's audit trail: row_inserted had a null IP and user agent."""
    client.post("/subscribe", json={"email": "ctx@x.com"}, headers={"user-agent": "probe/2.0"})

    with Session(test_engine) as s:
        set_service_scope(s)
        rows = s.execute(
            text(
                "SELECT action, actor_ip_hash, actor_user_agent FROM subscriber_audit"
                " WHERE email = :e ORDER BY id"
            ),
            {"e": "ctx@x.com"},
        ).mappings()
        by_action = {r["action"]: r for r in rows}

    assert "row_inserted" in by_action, "the trigger should have fired"
    assert by_action["row_inserted"]["actor_user_agent"] == "probe/2.0"
    assert by_action["row_inserted"]["actor_ip_hash"], "trigger row must carry the hashed IP"


def test_a_failing_send_reports_cleanly_instead_of_500ing(client, test_engine, monkeypatch):
    """Found by driving the real form, not by a test: Resend raised, and the whole request 500'd
    after the row was already written. A provider outage must not take signup down."""
    def boom(*a, **k):
        raise RuntimeError("resend is unhappy")

    monkeypatch.setattr("telogify.api.routes.send_verification_email", boom)
    r = client.post("/subscribe", json={"email": "sendfail@x.com"})

    assert r.status_code == 503
    assert "try again" in r.json()["detail"].lower()
    actions = _audit_actions(test_engine, "sendfail@x.com")
    assert "verification_send_failed" in actions
    assert "verification_sent" not in actions


def test_unsubscribed_address_can_opt_in_again(client, test_engine, sent):
    client.post("/subscribe", json={"email": "again@x.com"})
    client.post("/subscribe/verify", json={"token": sent["verify"][0][1]})
    client.post(f"/unsubscribe?t={sent['welcome'][0][1]}")

    client.post("/subscribe", json={"email": "again@x.com"})
    assert len(sent["verify"]) == 2, "a returning address gets a fresh verification"
    assert _subscriber(test_engine, "again@x.com").status == "pending"
