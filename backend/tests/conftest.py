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
