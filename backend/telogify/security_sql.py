"""Row-level security, audit triggers and append-only enforcement for the subscriber tables.

This lives here rather than inside the migration because `tests/conftest.py` builds the test
schema with `SQLModel.metadata.create_all()`, not Alembic. DDL that existed only in a migration
would be absent under pytest, so the policies and triggers would be production-only fiction and
every test asserting them would pass vacuously. Both paths apply this same list.

Every statement is idempotent (CREATE OR REPLACE / DROP ... IF EXISTS first), because the
migration runs against a live DB while the test fixture re-applies it after each drop_all.

What it enforces, and what it honestly does not:

- `subscriber` gets ENABLE + **FORCE** row level security, with policies keyed off
  per-transaction GUCs (`app.scope`, `app.actor_key`) set by `db.py`.
- **FORCE alone is not enough, and this was proven the hard way.** FORCE subjects the table
  *owner* to policies, but superusers bypass row security unconditionally, and both local
  Homebrew Postgres and Railway's Postgres plugin hand out a superuser. With FORCE set and no
  GUC at all, a superuser session still saw every row. The policies were decorative.
- The fix is `SUBSCRIBER_RLS_ROLE`: a NOSUPERUSER **NOLOGIN** role created here, that the
  restricted request path drops into with `SET LOCAL ROLE` (see `db.py: set_subscriber_context`).
  RLS keys off `current_user`, so acting as a non-superuser makes the policies apply for real.
  NOLOGIN means it is an RLS identity only and cannot be used to open a connection, so there is
  no second DSN, no new env var and nothing to provision on Railway.
- Unset GUCs mean `current_setting(..., true)` returns NULL, every policy branch is NULL, and the
  row is invisible. Fail-closed *within the restricted path*: a scoped handler that forgets its
  WHERE clause returns zero rows rather than the whole list. That is the guarantee this buys.
- **It is still not a boundary against a compromised app process.** That process can
  `RESET ROLE` or set the GUC to anything it likes. Real containment needs the app to *connect*
  as a low-privilege role, which was considered and declined because it needs a second DSN and
  per-environment provisioning. What is bought here is protection against a query bug, not
  against an attacker who already has code execution.
- The audit table's immutability is the genuinely owner-proof guarantee, because a BEFORE trigger
  that RAISEs cannot be bypassed by any role, owner or otherwise. Its RLS policy is a no-op for
  the owner today and exists so that introducing a low-privilege role later is config, not
  redesign.
"""

#: The RLS identity the restricted request path assumes. NOLOGIN: it exists to be SET ROLE'd
#: into, never to connect as. CREATE ROLE has no IF NOT EXISTS, hence the DO block, and roles
#: are cluster-wide so this must tolerate already existing from another database.
SUBSCRIBER_RLS_ROLE = "telogify_subscriber_rls"

# CREATE ROLE needs CREATEROLE or superuser, which the deploy's DB user may not have. This
# migration runs inside railway.toml's start command, so raising here would crash-loop the API
# and take the whole site down over a hardening feature. Degrade instead: warn, skip, and let
# db.py notice the role is missing at runtime. The audit trigger and append-only guarantee,
# which are the stronger of the two protections, do not depend on this role at all.
_RLS_ROLE = f"""
DO $do$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{SUBSCRIBER_RLS_ROLE}') THEN
        BEGIN
            CREATE ROLE {SUBSCRIBER_RLS_ROLE} NOSUPERUSER NOLOGIN NOINHERIT;
        EXCEPTION WHEN insufficient_privilege THEN
            RAISE WARNING 'Could not create {SUBSCRIBER_RLS_ROLE} (needs CREATEROLE). Row level '
                          'security will not be enforced; audit triggers are unaffected.';
        END;
    END IF;
END $do$;
"""

# No DELETE: unsubscribing flips `status`, it never removes the consent record. The audit table
# is deliberately absent here, so a restricted session cannot read or write the log at all --
# rate limiting and security-event logging run in service scope before the drop into this role.
# Guarded by the same existence check, since the role may not have been creatable above.
_RLS_ROLE_GRANTS = f"""
DO $do$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{SUBSCRIBER_RLS_ROLE}') THEN
        GRANT SELECT, INSERT, UPDATE ON subscriber TO {SUBSCRIBER_RLS_ROLE};
        GRANT USAGE, SELECT ON SEQUENCE subscriber_id_seq TO {SUBSCRIBER_RLS_ROLE};
    END IF;
END $do$;
"""

# A request may touch a subscriber row only if it proves it knows that row's email (signup),
# that row's verification token hash (verify), or that row's id via a signed unsubscribe link.
# One rule, one place, reused by USING and WITH CHECK so reads and writes cannot drift apart.
_VISIBILITY_FN = """
CREATE OR REPLACE FUNCTION telogify_subscriber_visible(
    p_email text, p_verify_hash text, p_id integer
) RETURNS boolean LANGUAGE sql STABLE AS $fn$
    SELECT current_setting('app.scope', true) = 'service'
        OR current_setting('app.actor_key', true) = 'email:' || p_email
        OR (p_verify_hash IS NOT NULL
            AND current_setting('app.actor_key', true) = 'vtok:' || p_verify_hash)
        OR (p_id IS NOT NULL
            AND current_setting('app.actor_key', true) = 'sub:' || p_id::text);
$fn$;
"""

# SECURITY DEFINER so the insert lands regardless of the caller's grants on the audit table.
# NEW is unassigned during DELETE (and OLD during INSERT), so identity is resolved per-branch
# rather than with COALESCE(NEW.id, OLD.id), which raises "record not assigned yet".
# verify_token_hash is stripped from both payloads: a log that copies the credential defeats
# the point of only ever storing its hash.
_AUDIT_FN = """
CREATE OR REPLACE FUNCTION telogify_audit_subscriber() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER AS $fn$
DECLARE
    v_action text;
    v_old jsonb;
    v_new jsonb;
    v_id integer;
    v_email text;
BEGIN
    IF TG_OP = 'DELETE' THEN
        v_action := 'row_deleted';
        v_old := to_jsonb(OLD) - 'verify_token_hash';
        v_id := OLD.id;
        v_email := OLD.email;
    ELSIF TG_OP = 'UPDATE' THEN
        v_action := 'row_updated';
        v_old := to_jsonb(OLD) - 'verify_token_hash';
        v_new := to_jsonb(NEW) - 'verify_token_hash';
        v_id := NEW.id;
        v_email := NEW.email;
    ELSE
        v_action := 'row_inserted';
        v_new := to_jsonb(NEW) - 'verify_token_hash';
        v_id := NEW.id;
        v_email := NEW.email;
    END IF;

    INSERT INTO subscriber_audit (
        subscriber_id, email, action, old_data, new_data,
        actor_key, actor_ip_hash, actor_user_agent, created_at
    ) VALUES (
        v_id, v_email, v_action, v_old::json, v_new::json,
        NULLIF(current_setting('app.actor_key', true), ''),
        NULLIF(current_setting('app.actor_ip_hash', true), ''),
        NULLIF(current_setting('app.actor_user_agent', true), ''),
        (now() AT TIME ZONE 'utc')
    );
    RETURN NULL;
END $fn$;
"""

# No role can talk its way past a BEFORE trigger that raises, owner and superuser included.
# This, not RLS, is what actually makes the log read-only. DROP TABLE is DDL and unaffected,
# so conftest's drop_all still works.
_IMMUTABLE_FN = """
CREATE OR REPLACE FUNCTION telogify_audit_immutable() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    RAISE EXCEPTION 'subscriber_audit is append-only (attempted %)', TG_OP;
END $fn$;
"""

SUBSCRIBER_SECURITY_DDL: list[str] = [
    _RLS_ROLE,
    _RLS_ROLE_GRANTS,
    _VISIBILITY_FN,
    _AUDIT_FN,
    _IMMUTABLE_FN,
    "ALTER TABLE subscriber ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE subscriber FORCE ROW LEVEL SECURITY",
    "DROP POLICY IF EXISTS subscriber_self ON subscriber",
    """
    CREATE POLICY subscriber_self ON subscriber
        USING (telogify_subscriber_visible(email, verify_token_hash, id))
        WITH CHECK (telogify_subscriber_visible(email, verify_token_hash, id))
    """,
    "DROP TRIGGER IF EXISTS subscriber_audit_trg ON subscriber",
    """
    CREATE TRIGGER subscriber_audit_trg
        AFTER INSERT OR UPDATE OR DELETE ON subscriber
        FOR EACH ROW EXECUTE FUNCTION telogify_audit_subscriber()
    """,
    "ALTER TABLE subscriber_audit ENABLE ROW LEVEL SECURITY",
    "DROP POLICY IF EXISTS subscriber_audit_service_read ON subscriber_audit",
    """
    CREATE POLICY subscriber_audit_service_read ON subscriber_audit
        FOR SELECT USING (current_setting('app.scope', true) = 'service')
    """,
    # The trigger writes via SECURITY DEFINER, so no INSERT policy is granted to callers.
    "DROP TRIGGER IF EXISTS subscriber_audit_immutable_trg ON subscriber_audit",
    """
    CREATE TRIGGER subscriber_audit_immutable_trg
        BEFORE UPDATE OR DELETE ON subscriber_audit
        FOR EACH ROW EXECUTE FUNCTION telogify_audit_immutable()
    """,
    "REVOKE UPDATE, DELETE ON subscriber_audit FROM PUBLIC",
]

SUBSCRIBER_SECURITY_DOWN_DDL: list[str] = [
    # Revoke but never DROP the role: roles are cluster-wide, so telogify_dev and telogify_test
    # share one, and dropping it here would break the other database mid-run.
    f"REVOKE ALL ON subscriber FROM {SUBSCRIBER_RLS_ROLE}",
    f"REVOKE ALL ON SEQUENCE subscriber_id_seq FROM {SUBSCRIBER_RLS_ROLE}",
    "DROP TRIGGER IF EXISTS subscriber_audit_immutable_trg ON subscriber_audit",
    "DROP TRIGGER IF EXISTS subscriber_audit_trg ON subscriber",
    "DROP POLICY IF EXISTS subscriber_audit_service_read ON subscriber_audit",
    "DROP POLICY IF EXISTS subscriber_self ON subscriber",
    "ALTER TABLE subscriber NO FORCE ROW LEVEL SECURITY",
    "ALTER TABLE subscriber DISABLE ROW LEVEL SECURITY",
    "ALTER TABLE subscriber_audit DISABLE ROW LEVEL SECURITY",
    "DROP FUNCTION IF EXISTS telogify_audit_immutable()",
    "DROP FUNCTION IF EXISTS telogify_audit_subscriber()",
    "DROP FUNCTION IF EXISTS telogify_subscriber_visible(text, text, integer)",
]
