"""Verifies Resend's webhook signatures (Svix-based) so bounce/complaint events can be trusted.

Stdlib only (hmac, hashlib, base64, time) -- no `svix` dependency, matching subscriptions.py's
own "no new dependencies: stdlib secrets/hmac" precedent. The algorithm below is Svix's
documented manual-verification scheme, not a guess: https://docs.svix.com/receiving/verifying-payloads/how-manual

Signature must be checked against the RAW request body bytes, never a re-parsed/re-serialized
JSON object -- Svix's own docs flag this as the most common way a correct-looking implementation
silently fails, since a re-serialized body rarely round-trips byte-for-byte (key order, spacing).
"""

from __future__ import annotations

import hashlib
import hmac
import time
from base64 import b64decode, b64encode

from telogify.config import settings

#: Svix's own replay-protection window: reject anything with an older/newer timestamp than this.
TIMESTAMP_TOLERANCE_SECONDS = 5 * 60


def verify(*, body: bytes, svix_id: str, svix_timestamp: str, svix_signature: str) -> bool:
    """True only if the signature is valid AND the secret is configured.

    An unset secret means "verify nothing," and unverified means "trust nothing" -- there is no
    dev-mode bypass here the way recaptcha_secret has one, because there is no local-testing
    scenario where accepting an unsigned payload that can flip a subscriber's status is safe.
    """
    if not settings.resend_webhook_secret:
        return False

    try:
        timestamp = int(svix_timestamp)
    except (TypeError, ValueError):
        return False
    if abs(time.time() - timestamp) > TIMESTAMP_TOLERANCE_SECONDS:
        return False

    secret_bytes = b64decode(settings.resend_webhook_secret.removeprefix("whsec_"))
    signed_content = f"{svix_id}.{svix_timestamp}.".encode() + body
    expected = b64encode(hmac.new(secret_bytes, signed_content, hashlib.sha256).digest())

    # svix-signature is space-delimited "v1,<base64sig>" entries; any match is valid (Svix
    # rotates/multi-signs during secret rollover), so check every candidate.
    for candidate in svix_signature.split():
        _, _, sig = candidate.partition(",")
        if sig and hmac.compare_digest(sig.encode(), expected):
            return True
    return False
