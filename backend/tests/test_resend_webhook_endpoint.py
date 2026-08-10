"""POST /webhooks/resend: signature enforcement, suppression on bounce/complaint, and that a
suppressed address stays suppressed against a repeat /subscribe.

Payload shapes are Resend's own documented examples for email.bounced / email.complained (see
resend_webhooks.py's docstring), not a captured real event -- there is no live webhook hitting
this endpoint yet, which is the one thing only a real deploy can fully confirm.
"""

import hashlib
import hmac
import json
import secrets
import time
from base64 import b64decode, b64encode

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from telogify.api.main import app
from telogify.api.routes import get_session
from telogify.db import set_service_scope
from telogify.models import Subscriber

# Generated, not a literal secret-shaped string in source -- gitleaks correctly can't distinguish
# a hardcoded example secret from a real one. Only needs to round-trip through this file's own
# _headers()/verify(), so it doesn't matter that it isn't Svix's published example value.
SECRET = "whsec_" + b64encode(secrets.token_bytes(32)).decode()


def _headers(body: bytes, svix_id: str = "msg_1") -> dict:
    ts = str(int(time.time()))
    secret_bytes = b64decode(SECRET.removeprefix("whsec_"))
    signed = f"{svix_id}.{ts}.".encode() + body
    sig = b64encode(hmac.new(secret_bytes, signed, hashlib.sha256).digest()).decode()
    return {"svix-id": svix_id, "svix-timestamp": ts, "svix-signature": f"v1,{sig}"}


def _bounced_payload(to: str) -> bytes:
    # Shape per Resend's documented email.bounced example.
    return json.dumps({
        "type": "email.bounced",
        "created_at": "2026-01-01T00:00:00.000Z",
        "data": {"email_id": "e1", "from": "Telogify <pitwall@paddock.telogify.com>", "to": [to],
                 "subject": "test"},
    }).encode()


def _complained_payload(to: str) -> bytes:
    return json.dumps({
        "type": "email.complained",
        "created_at": "2026-01-01T00:00:00.000Z",
        "data": {"email_id": "e2", "from": "Telogify <pitwall@paddock.telogify.com>", "to": [to],
                 "subject": "test"},
    }).encode()


@pytest.fixture
def client(test_engine, monkeypatch):
    monkeypatch.setattr("telogify.subscriptions.settings.recaptcha_secret", "")
    monkeypatch.setattr("telogify.resend_webhooks.settings.resend_webhook_secret", SECRET)

    def override():
        with Session(test_engine) as s:
            yield s

    app.dependency_overrides[get_session] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def _make_confirmed_subscriber(test_engine, email: str) -> None:
    with Session(test_engine) as s:
        set_service_scope(s)
        s.add(Subscriber(email=email, status="confirmed"))
        s.commit()


def _status(test_engine, email: str) -> str | None:
    with Session(test_engine) as s:
        set_service_scope(s)
        sub = s.exec(select(Subscriber).where(Subscriber.email == email)).first()
        return sub.status if sub else None


def test_missing_signature_is_rejected(client):
    r = client.post("/webhooks/resend", content=_bounced_payload("a@x.com"))
    assert r.status_code == 401


def test_wrong_secret_is_rejected(client, test_engine):
    _make_confirmed_subscriber(test_engine, "bounce1@x.com")
    body = _bounced_payload("bounce1@x.com")
    ts = str(int(time.time()))
    bad_sig = b64encode(hmac.new(b"wrong-key", f"msg_1.{ts}.".encode() + body, hashlib.sha256).digest()).decode()
    r = client.post("/webhooks/resend", content=body,
                    headers={"svix-id": "msg_1", "svix-timestamp": ts, "svix-signature": f"v1,{bad_sig}"})
    assert r.status_code == 401
    assert _status(test_engine, "bounce1@x.com") == "confirmed"  # untouched


def test_bounced_event_suppresses_the_matching_subscriber(client, test_engine):
    _make_confirmed_subscriber(test_engine, "bounce2@x.com")
    body = _bounced_payload("bounce2@x.com")
    r = client.post("/webhooks/resend", content=body, headers=_headers(body))
    assert r.status_code == 200
    assert _status(test_engine, "bounce2@x.com") == "bounced"


def test_complained_event_suppresses_the_matching_subscriber(client, test_engine):
    _make_confirmed_subscriber(test_engine, "complain1@x.com")
    body = _complained_payload("complain1@x.com")
    r = client.post("/webhooks/resend", content=body, headers=_headers(body))
    assert r.status_code == 200
    assert _status(test_engine, "complain1@x.com") == "complained"


def test_an_unrecognized_event_type_is_a_noop_200(client, test_engine):
    """Resend retries non-2xx responses, so an event we don't act on must still 200."""
    _make_confirmed_subscriber(test_engine, "opened1@x.com")
    body = json.dumps({"type": "email.opened", "data": {"to": ["opened1@x.com"]}}).encode()
    r = client.post("/webhooks/resend", content=body, headers=_headers(body))
    assert r.status_code == 200
    assert _status(test_engine, "opened1@x.com") == "confirmed"  # untouched


def test_an_address_not_in_the_table_is_a_noop_not_an_error(client):
    body = _bounced_payload("never-signed-up@x.com")
    r = client.post("/webhooks/resend", content=body, headers=_headers(body))
    assert r.status_code == 200


def test_a_bounced_address_cannot_be_reactivated_by_resubscribing(client, test_engine):
    _make_confirmed_subscriber(test_engine, "bounce3@x.com")
    body = _bounced_payload("bounce3@x.com")
    client.post("/webhooks/resend", content=body, headers=_headers(body))
    assert _status(test_engine, "bounce3@x.com") == "bounced"

    r = client.post("/subscribe", json={"email": "bounce3@x.com"})
    assert r.status_code == 200 and r.json() == {"status": "check_your_inbox"}
    assert _status(test_engine, "bounce3@x.com") == "bounced", "must not flip back to pending"
