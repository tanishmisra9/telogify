"""Engine + session factory."""

from collections.abc import Iterator

import numpy as np
from psycopg2.extensions import AsIs, register_adapter
from sqlmodel import Session, create_engine

from telogify.config import settings

# FastF1/numpy hands back numpy scalars; psycopg2 cannot adapt them and renders their repr
# (e.g. np.float64(312.0)) into SQL. Coerce any numpy scalar to its native Python value so
# every extractor's DB writes are safe, not just the one that first tripped on it.
def _adapt_numpy(value):
    return AsIs(value.item())


for _np_type in (np.float64, np.float32, np.int64, np.int32, np.int16, np.bool_):
    register_adapter(_np_type, _adapt_numpy)


# pool_size/max_overflow sized above SQLAlchemy's 5+10 default so `run-insights --workers`
# (default 4, each holding a session per tool call) has headroom without silently queuing.
engine = create_engine(settings.database_url, echo=False, pool_size=10, max_overflow=20)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
