"""Proves the DB-level guarantees in security_sql.py actually hold.

These run against real Postgres because that is the only place the triggers and policies exist.
Each test is written so it FAILS if the corresponding DDL is dropped, rather than passing
vacuously: the audit assertions read rows the trigger wrote, and the RLS assertions check that
a wrongly-scoped session sees nothing rather than checking that a correctly-scoped one sees
something.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, InternalError, ProgrammingError
from sqlmodel import Session, select

from telogify.db import set_db_context, set_service_scope, set_subscriber_context
from telogify.security_sql import SUBSCRIBER_RLS_ROLE
from telogify.models import Subscriber


def _audit_rows(session: Session, email: str) -> list[dict]:
    rows = session.execute(
        text(
            "SELECT action, old_data, new_data, actor_key, actor_ip_hash, actor_user_agent"
            " FROM subscriber_audit WHERE email = :e ORDER BY id"
        ),
        {"e": email},
    ).mappings()
    return [dict(r) for r in rows]


def test_trigger_audits_insert_update_and_delete(test_engine):
    with Session(test_engine) as s:
        set_service_scope(s)
        sub = Subscriber(email="a@x.com", status="pending")
        s.add(sub)
        s.commit()

        set_service_scope(s)
        sub = s.exec(select(Subscriber).where(Subscriber.email == "a@x.com")).one()
        sub.status = "confirmed"
        s.add(sub)
        s.commit()

        set_service_scope(s)
        sub = s.exec(select(Subscriber).where(Subscriber.email == "a@x.com")).one()
        s.delete(sub)
        s.commit()

        set_service_scope(s)
        rows = _audit_rows(s, "a@x.com")

    assert [r["action"] for r in rows] == ["row_inserted", "row_updated", "row_deleted"]
    assert rows[0]["new_data"]["status"] == "pending"
    assert rows[1]["old_data"]["status"] == "pending"
    assert rows[1]["new_data"]["status"] == "confirmed"
    assert rows[2]["old_data"]["status"] == "confirmed"
    assert rows[2]["new_data"] is None


def test_audit_payload_never_contains_the_token_hash(test_engine):
    """A log that copies the credential defeats the point of only storing its hash."""
    with Session(test_engine) as s:
        set_service_scope(s)
        s.add(Subscriber(email="b@x.com", verify_token_hash="SECRETHASH"))
        s.commit()

        set_service_scope(s)
        rows = _audit_rows(s, "b@x.com")

    assert rows and "verify_token_hash" not in rows[0]["new_data"]
    assert "SECRETHASH" not in str(rows)


def test_trigger_records_actor_context(test_engine):
    with Session(test_engine) as s:
        set_db_context(
            s, actor_key="email:c@x.com", actor_ip_hash="deadbeef", actor_user_agent="pytest/1.0"
        )
        s.add(Subscriber(email="c@x.com"))
        s.commit()

        set_service_scope(s)
        rows = _audit_rows(s, "c@x.com")

    assert rows[0]["actor_key"] == "email:c@x.com"
    assert rows[0]["actor_ip_hash"] == "deadbeef"
    assert rows[0]["actor_user_agent"] == "pytest/1.0"


@pytest.mark.parametrize("statement", [
    "UPDATE subscriber_audit SET action = 'tampered'",
    "DELETE FROM subscriber_audit",
])
def test_audit_log_is_append_only(test_engine, statement):
    with Session(test_engine) as s:
        set_service_scope(s)
        s.add(Subscriber(email="d@x.com"))
        s.commit()

    with Session(test_engine) as s:
        set_service_scope(s)
        with pytest.raises((InternalError, ProgrammingError, DBAPIError)) as exc:
            s.execute(text(statement))
            s.commit()
        assert "append-only" in str(exc.value)

    # and the row survived the attempt
    with Session(test_engine) as s:
        set_service_scope(s)
        assert _audit_rows(s, "d@x.com")


def test_restricted_session_without_a_matching_key_sees_nothing(test_engine):
    """Fail-closed inside the restricted path: a handler that drops into the RLS role but whose
    actor_key matches no row gets zero rows, never the whole list. This is the property the
    whole RLS design exists to buy."""
    with Session(test_engine) as s:
        set_service_scope(s)
        s.add(Subscriber(email="e@x.com"))
        s.commit()

    with Session(test_engine) as s:
        set_subscriber_context(s, actor_key="email:nobody@nowhere.com")
        assert s.exec(select(Subscriber)).all() == []

    with Session(test_engine) as s:
        set_subscriber_context(s, actor_key="")
        assert s.exec(select(Subscriber)).all() == []


def test_superuser_without_set_role_bypasses_rls_by_design(test_engine):
    """Pins the documented limitation so it is not mistaken for a bug later.

    Postgres superusers bypass row security unconditionally, and FORCE only subjects the table
    *owner*. That is precisely why set_subscriber_context issues SET LOCAL ROLE. If this test
    ever starts failing, the connection role changed to a non-superuser, and the SET LOCAL ROLE
    machinery could then be simplified away.
    """
    with Session(test_engine) as s:
        set_service_scope(s)
        s.add(Subscriber(email="bypass@x.com"))
        s.commit()

    with Session(test_engine) as s:  # no scope, no role: still a superuser connection
        is_superuser = s.execute(
            text("SELECT usesuper FROM pg_user WHERE usename = current_user")
        ).scalar()
        rows = s.exec(select(Subscriber)).all()

    if is_superuser:
        assert rows, "superuser unexpectedly filtered by RLS; see docstring"
    else:
        assert rows == []


def test_email_scoped_session_cannot_see_another_subscriber(test_engine):
    with Session(test_engine) as s:
        set_service_scope(s)
        s.add(Subscriber(email="mine@x.com"))
        s.add(Subscriber(email="theirs@x.com"))
        s.commit()

    with Session(test_engine) as s:
        set_subscriber_context(s, actor_key="email:mine@x.com")
        visible = [row.email for row in s.exec(select(Subscriber)).all()]

    assert visible == ["mine@x.com"]


def test_token_scoped_session_sees_only_its_own_row(test_engine):
    with Session(test_engine) as s:
        set_service_scope(s)
        s.add(Subscriber(email="tok@x.com", verify_token_hash="HASH_ONE"))
        s.add(Subscriber(email="other@x.com", verify_token_hash="HASH_TWO"))
        s.commit()

    with Session(test_engine) as s:
        set_subscriber_context(s, actor_key="vtok:HASH_ONE")
        visible = [row.email for row in s.exec(select(Subscriber)).all()]

    assert visible == ["tok@x.com"]


def test_null_token_hash_does_not_match_a_null_actor_key(test_engine):
    """Guards the `p_verify_hash IS NOT NULL` branch: rows with no token must not become
    visible to a session whose actor_key happens to be absent or malformed."""
    with Session(test_engine) as s:
        set_service_scope(s)
        s.add(Subscriber(email="notoken@x.com", verify_token_hash=None))
        s.commit()

    with Session(test_engine) as s:
        set_subscriber_context(s, actor_key="vtok:")
        assert s.exec(select(Subscriber)).all() == []


def test_context_does_not_leak_across_pooled_sessions(test_engine):
    """SET LOCAL semantics are load-bearing: the engine pools connections, so a session-level
    GUC would hand one request's identity to the next request that recycles the connection."""
    with Session(test_engine) as s:
        set_service_scope(s)
        s.add(Subscriber(email="leak@x.com"))
        s.commit()

    with Session(test_engine) as s:
        set_subscriber_context(s, actor_key="email:leak@x.com")
        s.exec(select(Subscriber)).all()
        s.commit()  # transaction ends here, so GUCs and the role must revert

    with Session(test_engine) as s:
        leaked = s.execute(
            text(
                "SELECT current_setting('app.actor_key', true), current_user::text,"
                " current_setting('app.actor_ip_hash', true)"
            )
        ).one()
        assert leaked[0] in (None, "")
        assert leaked[1] != SUBSCRIBER_RLS_ROLE, "SET LOCAL ROLE leaked past its transaction"
        assert leaked[2] in (None, "")
