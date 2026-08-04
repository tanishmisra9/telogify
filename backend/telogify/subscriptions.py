"""Double opt-in mechanics: email normalization, tokens, rate limiting, captcha.

Deliberately one module rather than four. Each piece is a handful of lines, they are only ever
used together by the four subscriber endpoints, and splitting them would mean four files whose
combined content fits on one screen.

Two token schemes, because they have genuinely different requirements:

- **Verification** tokens must expire and be single-use, so they need DB state. A random
  `secrets.token_urlsafe(32)` is issued, only its SHA-256 is stored, and confirmation clears it.
  A DB dump therefore cannot confirm anyone.
- **Unsubscribe** tokens must survive forever and be reconstructable at every send, so a
  hash-only column could not work and storing them in plaintext would be a stored secret for no
  benefit. They are instead derived: `id.hmac(secret, id)`, verified by recomputation, holding
  no DB state at all. Rotating `SUBSCRIBER_TOKEN_SECRET` invalidates every outstanding link.

No `email-validator`/`pydantic.EmailStr` (not installed, and a regex plus a real confirmation
email is the actual validation), no `itsdangerous` (stdlib `hmac` covers it), no `slowapi` or
Redis (the audit table is already written on every attempt, so counting it is free).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
from datetime import datetime, timedelta

import httpx
from sqlalchemy import text
from sqlmodel import Session

from telogify.config import settings

#: How long a verification link stays good. Stated in the email, so changing it means changing
#: the copy in emails_optin too.
VERIFY_TOKEN_TTL_HOURS = 24

#: Rate limits, counted against subscriber_audit. Not settings: they do not vary per deploy,
#: and a knob nobody turns is just another thing to get wrong.
MAX_SIGNUPS_PER_IP_PER_HOUR = 5
MAX_VERIFY_SENDS_PER_EMAIL_PER_HOUR = 3

#: reCAPTCHA v3 returns a 0.0-1.0 score; 0.5 is Google's documented default threshold.
RECAPTCHA_MIN_SCORE = 0.5
RECAPTCHA_VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"
RECAPTCHA_ACTION = "subscribe"

# Deliberately permissive within one address: the confirmation email is the real validation, so
# this only needs to reject things that are obviously not addresses. Length cap first, because
# an unbounded input is the part that actually matters at a trust boundary.
_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s.]+(\.[^@\s.]+)+$")
MAX_EMAIL_LENGTH = 254  # RFC 5321


def normalize_email(raw: str) -> str | None:
    """Trim + lowercase, or None if it is not plausibly an address.

    Lowercasing is what makes the unique index a real dedupe: without it Bob@x.com and
    bob@x.com are two subscribers and one of them can never unsubscribe the other.
    """
    if not raw:
        return None
    cleaned = raw.strip().lower()
    if len(cleaned) > MAX_EMAIL_LENGTH or not _EMAIL_RE.match(cleaned):
        return None
    return cleaned


_warned_about_fallback_key = False


def _signing_key() -> bytes:
    """The HMAC key, falling back to one derived from DATABASE_URL when none is configured.

    An unset SUBSCRIBER_TOKEN_SECRET used to mean signing with an empty key, which is not a weak
    secret but no secret at all: anyone could compute a valid unsubscribe token for any
    subscriber id and unsubscribe a stranger. Deriving from DATABASE_URL instead gives something
    stable across restarts and instances (so existing links keep working) and genuinely unknown
    to outsiders in production, where the URL carries a generated password.

    This is a floor, not a substitute. Locally DATABASE_URL has no password and the derived key
    is guessable, which is fine there and is why the warning fires anyway. Set the real variable
    before sending anything: switching to it invalidates every token minted under the fallback.
    """
    global _warned_about_fallback_key
    if settings.subscriber_token_secret:
        return settings.subscriber_token_secret.encode()
    if not _warned_about_fallback_key:
        _warned_about_fallback_key = True
        logging.getLogger(__name__).warning(
            "SUBSCRIBER_TOKEN_SECRET is unset; deriving a fallback signing key from "
            "DATABASE_URL. Set a real secret. Doing so later invalidates unsubscribe links "
            "already sent."
        )
    return hashlib.sha256(f"telogify-fallback-key:{settings.database_url}".encode()).digest()


def _hmac(message: str) -> str:
    return hmac.new(_signing_key(), message.encode(), hashlib.sha256).hexdigest()


def hash_ip(ip: str | None) -> str | None:
    """Rate limiting needs to recognise a repeat visitor, not to know who they are, so the log
    stores an HMAC and never a raw address."""
    return _hmac(f"ip:{ip}") if ip else None


def new_verify_token() -> tuple[str, str, datetime]:
    """Returns (plaintext for the email, hash to store, expiry)."""
    token = secrets.token_urlsafe(32)
    expires = datetime.utcnow() + timedelta(hours=VERIFY_TOKEN_TTL_HOURS)
    return token, hash_token(token), expires


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def unsubscribe_token(subscriber_id: int) -> str:
    """Stateless, permanent, verified by recomputation. Format: `{id}.{sig}`."""
    return f"{subscriber_id}.{_hmac(f'unsub:{subscriber_id}')}"


def parse_unsubscribe_token(token: str) -> int | None:
    """The subscriber id the token vouches for, or None if it does not verify."""
    raw_id, _, signature = (token or "").partition(".")
    if not raw_id.isdigit() or not signature:
        return None
    subscriber_id = int(raw_id)
    # compare_digest, not ==, so a timing signal cannot be used to forge a signature byte by byte.
    if not hmac.compare_digest(signature, _hmac(f"unsub:{subscriber_id}")):
        return None
    return subscriber_id


def _count_recent(session: Session, column: str, value: str, actions: tuple[str, ...]) -> int:
    row = session.execute(
        text(
            f"SELECT count(*) FROM subscriber_audit WHERE {column} = :value"
            " AND action = ANY(:actions) AND created_at > :cutoff"
        ),
        {
            "value": value,
            "actions": list(actions),
            "cutoff": datetime.utcnow() - timedelta(hours=1),
        },
    ).scalar()
    return int(row or 0)


def signup_rate_limited(session: Session, *, ip_hash: str | None, email: str) -> bool:
    """True if this IP or this address has had enough for one hour.

    Counted against subscriber_audit, which is written on every attempt anyway. Must run in
    service scope: the restricted RLS role has no access to the audit table at all.
    """
    if ip_hash and _count_recent(
        session, "actor_ip_hash", ip_hash, ("signup_requested", "blocked_rate_limit")
    ) >= MAX_SIGNUPS_PER_IP_PER_HOUR:
        return True
    return _count_recent(
        session, "email", email, ("verification_sent",)
    ) >= MAX_VERIFY_SENDS_PER_EMAIL_PER_HOUR


def verify_recaptcha(token: str, remote_ip: str | None = None) -> bool:
    """Score-based v3 check. Empty secret means local dev, where it is skipped.

    `require_signup_secrets()` guarantees the secret is present in production, so this cannot
    silently degrade to "always pass" on a real deployment.
    """
    if not settings.recaptcha_secret:
        return True
    if not token:
        return False
    payload = {"secret": settings.recaptcha_secret, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip
    try:
        response = httpx.post(RECAPTCHA_VERIFY_URL, data=payload, timeout=5.0)
        result = response.json()
    except (httpx.HTTPError, ValueError):
        # Google being unreachable must not take signup down, and must not wave everyone
        # through either. Fail closed: the visitor can retry.
        return False
    # The action check matters: without it a token minted on any other page of the site (or any
    # other site sharing the key) would be replayable here.
    return bool(
        result.get("success")
        and result.get("action") == RECAPTCHA_ACTION
        and float(result.get("score", 0.0)) >= RECAPTCHA_MIN_SCORE
    )
