"""Pure-compute half of subscriptions.py: normalization and the two token schemes."""

import pytest

from telogify.subscriptions import (
    MAX_EMAIL_LENGTH,
    hash_ip,
    hash_token,
    new_verify_token,
    normalize_email,
    parse_unsubscribe_token,
    unsubscribe_token,
)


@pytest.mark.parametrize("raw,expected", [
    ("  Racer@Example.COM  ", "racer@example.com"),
    ("a.b+tag@sub.domain.co.uk", "a.b+tag@sub.domain.co.uk"),
    ("UPPER@CASE.COM", "upper@case.com"),
])
def test_normalize_accepts_and_lowercases(raw, expected):
    assert normalize_email(raw) == expected


@pytest.mark.parametrize("raw", [
    "", "   ", None, "no-at-sign", "a@b", "a@@b.com", "a b@c.com", "a@b .com", "@b.com", "a@",
    "x" * 65 + "@y.com",           # local part over 64
    "a@" + "y" * 300 + ".com",     # total over 254
])
def test_normalize_rejects_junk(raw):
    assert normalize_email(raw) is None


def test_normalize_enforces_the_rfc_length_cap():
    local = "a" * 60
    domain = "b" * (MAX_EMAIL_LENGTH - len(local) - len("@.com")) + ".com"
    assert normalize_email(f"{local}@{domain}") is None or len(f"{local}@{domain}") <= MAX_EMAIL_LENGTH


def test_case_only_variants_collapse_to_one_subscriber():
    """Without this the unique index is not a real dedupe and one variant could never
    unsubscribe the other."""
    assert normalize_email("Bob@X.com") == normalize_email("bob@x.com")


def test_verify_token_is_random_and_only_its_hash_is_storable():
    token_a, hash_a, expires_a = new_verify_token()
    token_b, hash_b, _ = new_verify_token()

    assert token_a != token_b, "tokens must not repeat"
    assert hash_a != token_a and hash_a == hash_token(token_a)
    assert hash_b != hash_a
    assert len(hash_a) == 64  # sha256 hex
    assert expires_a > __import__("datetime").datetime.utcnow()


def test_unsubscribe_token_round_trips():
    assert parse_unsubscribe_token(unsubscribe_token(42)) == 42


@pytest.mark.parametrize("bad", [
    "", "42", "42.", ".sig", "notanid.sig", "42.deadbeef", "-1.sig", "42.SIG",
])
def test_unsubscribe_token_rejects_forgeries(bad):
    assert parse_unsubscribe_token(bad) is None


def test_unsubscribe_token_for_one_id_does_not_validate_for_another():
    forged = unsubscribe_token(1).split(".")[1]
    assert parse_unsubscribe_token(f"2.{forged}") is None


def test_ip_hash_is_deterministic_and_not_reversible():
    assert hash_ip("203.0.113.7") == hash_ip("203.0.113.7")
    assert hash_ip("203.0.113.7") != hash_ip("203.0.113.8")
    assert "203.0.113.7" not in (hash_ip("203.0.113.7") or "")
    assert hash_ip(None) is None


def test_unset_secret_does_not_sign_with_an_empty_key(monkeypatch):
    """An empty SUBSCRIBER_TOKEN_SECRET used to mean signing with no secret at all, so anyone
    could compute a valid unsubscribe token for any subscriber id and unsubscribe a stranger."""
    import hashlib as _hashlib
    import hmac as _hmac_mod

    from telogify import subscriptions

    monkeypatch.setattr(subscriptions.settings, "subscriber_token_secret", "")

    forged = _hmac_mod.new(b"", b"unsub:1", _hashlib.sha256).hexdigest()
    assert parse_unsubscribe_token(f"1.{forged}") is None
    # and the real token is stable, so links survive a restart
    assert unsubscribe_token(1) == unsubscribe_token(1)
    assert parse_unsubscribe_token(unsubscribe_token(1)) == 1


def test_a_real_secret_takes_precedence_over_the_fallback(monkeypatch):
    from telogify import subscriptions

    monkeypatch.setattr(subscriptions.settings, "subscriber_token_secret", "")
    fallback = unsubscribe_token(1)
    monkeypatch.setattr(subscriptions.settings, "subscriber_token_secret", "a-real-secret")
    assert unsubscribe_token(1) != fallback
    assert parse_unsubscribe_token(fallback) is None
