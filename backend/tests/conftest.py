import pytest
from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from telogify import models  # noqa: F401  (registers tables)
from telogify.config import settings
from telogify.db import set_service_scope
from telogify.security_sql import SUBSCRIBER_SECURITY_DDL

# Derive the test DB URL from the configured one by swapping the database name.
TEST_URL = settings.database_url.rsplit("/", 1)[0] + "/telogify_test"


@pytest.fixture(autouse=True)
def _no_live_recaptcha(monkeypatch):
    """Keep the suite offline and deterministic regardless of the developer's .env.

    `verify_recaptcha` posts to Google whenever RECAPTCHA_SECRET is set, so once a real secret
    landed in a local .env the suite started making live network calls and any test that posted
    to /subscribe began failing on a rejected fake token. Test outcomes must not depend on which
    credentials happen to be configured on the machine running them. Tests that care about the
    rejection path patch `verify_recaptcha` directly instead.
    """
    monkeypatch.setattr("telogify.subscriptions.settings.recaptcha_secret", "")


@pytest.fixture(autouse=True)
def _no_live_resend(monkeypatch):
    """Same principle again, for Resend: `email._send` only no-ops when RESEND_API_KEY is empty,
    and a developer's local .env carries a real key, so any test that reached a send path mailed
    real recipients (a@b.com bounced 22 times against the production domain's reputation).
    Tests that care about a send monkeypatch the `send_*` functions or `resend.Emails.send`.
    """
    monkeypatch.setattr("telogify.email.settings.resend_api_key", "")


@pytest.fixture(autouse=True)
def _valid_production_send_urls(monkeypatch):
    """Same principle as `_no_live_recaptcha` above, for `require_production_send_urls`
    (config.py): local `.env` deliberately sets ENVIRONMENT=production (so web_base_url resolves
    to the real telogify.com even in local dev) but may not have API_BASE_URL configured, which
    would otherwise make every send_digest-calling test's outcome depend on whichever developer's
    .env happens to be loaded. Tests that specifically exercise the guard override this back to a
    localhost value themselves.
    """
    monkeypatch.setattr("telogify.config.settings.api_base_url", "https://api.telogify.com")


@pytest.fixture
def test_engine():
    engine = create_engine(TEST_URL)
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    # create_all() does not know about triggers, policies or RLS, so apply the same DDL the
    # migration does. Without this the audit/RLS tests would pass vacuously against a schema
    # that has none of the machinery they claim to verify.
    with engine.begin() as conn:
        for stmt in SUBSCRIBER_SECURITY_DDL:
            conn.execute(text(stmt))
    yield engine
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(test_engine):
    with Session(test_engine) as session:
        # Mirrors get_session() in prod: a direct (non-request) session is a trusted caller.
        # subscriber is under FORCE RLS, so without this every subscriber row is invisible.
        set_service_scope(session)
        yield session
