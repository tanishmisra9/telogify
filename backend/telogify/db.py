"""Engine + session factory."""

from collections.abc import Iterator

import numpy as np
from psycopg2.extensions import AsIs, register_adapter
from sqlalchemy import text
from sqlmodel import Session, create_engine

from telogify.config import settings
from telogify.security_sql import SUBSCRIBER_RLS_ROLE

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


def set_db_context(session: Session, **gucs: str | None) -> None:
    """Set `app.*` GUCs for the CURRENT TRANSACTION only (see security_sql.py for the policies).

    The `true` third argument to set_config is SET LOCAL semantics, and it is load-bearing:
    `engine` pools connections, so a session-level GUC would leak one request's identity onto
    the next request that recycles that connection. Two consequences for callers: this must run
    before the work it scopes (it opens the transaction), and it is discarded by `commit()`, so
    scoped handlers set context, do the work, then commit exactly once at the end.

    Empty string rather than NULL for unset values, so `current_setting(..., true)` yields '' and
    every policy comparison is a clean false instead of a NULL that reads as "unset".
    """
    for key, value in gucs.items():
        session.execute(
            text("SELECT set_config(:key, :value, true)"),
            {"key": f"app.{key}", "value": value or ""},
        )


def set_service_scope(session: Session) -> None:
    """Grant the session full access to the subscriber tables.

    For trusted, non-request callers: the CLI, the digest sender, and every existing read-only
    route. The subscriber endpoints deliberately do NOT use this; they scope themselves to the
    one row the request proved it knows.
    """
    set_db_context(session, scope="service")


def set_subscriber_context(
    session: Session,
    *,
    actor_key: str,
    ip_hash: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Restrict the session to the single subscriber row `actor_key` proves knowledge of.

    `SET LOCAL ROLE` is the part that makes row level security real rather than decorative.
    Policies are evaluated against `current_user`, and superusers bypass RLS unconditionally --
    FORCE only subjects the table *owner*. Both local Postgres and Railway's plugin hand out a
    superuser, so without this the policies match nothing and every row stays visible. Verified
    directly: same policies, superuser saw every row, `SET LOCAL ROLE` saw exactly the one the
    GUC named.

    LOCAL, so it reverts with the transaction and the pooled connection goes back to the normal
    role for the next request. Call once at the start of a handler, commit exactly once at the
    end: both the role and the GUCs are discarded by `commit()`.
    """
    set_db_context(session, actor_key=actor_key, actor_ip_hash=ip_hash,
                   actor_user_agent=user_agent, scope="")
    session.execute(text(f"SET LOCAL ROLE {SUBSCRIBER_RLS_ROLE}"))


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        set_service_scope(session)
        yield session
