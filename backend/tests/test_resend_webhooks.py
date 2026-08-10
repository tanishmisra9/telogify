"""Svix signature verification: the pure function, tested against real Svix-shaped inputs.

Values are computed the same way Svix computes them (see resend_webhooks.py's docstring for the
algorithm source), not copied from a captured real webhook -- there is no live Resend webhook
hitting this endpoint yet, so this is the closest to real that's available without deploying.
"""

import hashlib
import hmac
import secrets
import time
from base64 import b64decode, b64encode

import pytest

from telogify import resend_webhooks
from telogify.config import settings

# Generated, not a literal, so this isn't a secret-shaped string sitting in source (gitleaks
# flagged Svix's own published example secret as a high-entropy finding, correctly if you can't
# tell it apart from a real one). Only has to round-trip through this file's own _sign()/verify().
SECRET = "whsec_" + b64encode(secrets.token_bytes(32)).decode()


def _sign(body: bytes, svix_id: str, svix_timestamp: str, secret: str = SECRET) -> str:
    secret_bytes = b64decode(secret.removeprefix("whsec_"))
    signed_content = f"{svix_id}.{svix_timestamp}.".encode() + body
    sig = b64encode(hmac.new(secret_bytes, signed_content, hashlib.sha256).digest()).decode()
    return f"v1,{sig}"


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setattr(settings, "resend_webhook_secret", SECRET)


def test_a_correctly_signed_payload_verifies():
    body = b'{"type":"email.bounced"}'
    ts = str(int(time.time()))
    sig = _sign(body, "msg_1", ts)
    assert resend_webhooks.verify(body=body, svix_id="msg_1", svix_timestamp=ts, svix_signature=sig)


def test_a_tampered_body_fails():
    body = b'{"type":"email.bounced"}'
    ts = str(int(time.time()))
    sig = _sign(body, "msg_1", ts)
    tampered = b'{"type":"email.delivered"}'
    assert not resend_webhooks.verify(
        body=tampered, svix_id="msg_1", svix_timestamp=ts, svix_signature=sig
    )


def test_signed_with_the_wrong_secret_fails():
    body = b'{"type":"email.bounced"}'
    ts = str(int(time.time()))
    wrong_secret = "whsec_" + b64encode(secrets.token_bytes(32)).decode()
    sig = _sign(body, "msg_1", ts, secret=wrong_secret)
    assert not resend_webhooks.verify(body=body, svix_id="msg_1", svix_timestamp=ts, svix_signature=sig)


def test_an_expired_timestamp_fails_even_with_a_valid_signature():
    body = b'{"type":"email.bounced"}'
    old_ts = str(int(time.time()) - 3600)  # 1 hour old, replay-window is 5 minutes
    sig = _sign(body, "msg_1", old_ts)
    assert not resend_webhooks.verify(
        body=body, svix_id="msg_1", svix_timestamp=old_ts, svix_signature=sig
    )


def test_no_secret_configured_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "resend_webhook_secret", "")
    body = b'{"type":"email.bounced"}'
    ts = str(int(time.time()))
    sig = _sign(body, "msg_1", ts)
    assert not resend_webhooks.verify(body=body, svix_id="msg_1", svix_timestamp=ts, svix_signature=sig)


def test_one_matching_signature_among_several_candidates_verifies():
    """Svix space-delimits multiple v1 signatures during secret rotation; any match is valid."""
    body = b'{"type":"email.bounced"}'
    ts = str(int(time.time()))
    real = _sign(body, "msg_1", ts)
    combined = f"v1,bm90dGhlcmVhbHNpZ25hdHVyZQ== {real}"
    assert resend_webhooks.verify(body=body, svix_id="msg_1", svix_timestamp=ts, svix_signature=combined)
