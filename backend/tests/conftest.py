import pytest
from sqlmodel import Session, SQLModel, create_engine

from telogify import models  # noqa: F401  (registers tables)
from telogify.config import settings

# Derive the test DB URL from the configured one by swapping the database name.
TEST_URL = settings.database_url.rsplit("/", 1)[0] + "/telogify_test"


@pytest.fixture
def test_engine():
    engine = create_engine(TEST_URL)
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(test_engine):
    with Session(test_engine) as session:
        yield session
