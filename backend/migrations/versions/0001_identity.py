"""Identity, tenancy, audit, approvals, jobs and usage.

Revision ID: 0001
"""

from alembic import op

from migrations.rls import GRANTS, ORG, USR, tenant_rls

revision = "0001"
down_revision = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext; CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # ---- global identity (no tenant column; only reachable through hashed tokens or own id) ----
    op.execute(
        """
        CREATE TABLE users (
          id uuid PRIMARY KEY,
          email citext NOT NULL UNIQUE,
          name text NOT NULL,
          password_hash text,
          created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE sessions (
          id uuid PRIMARY KEY,
          token_hash bytea NOT NULL UNIQUE,
          user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          active_org_id uuid,
          created_at timestamptz NOT NULL DEFAULT now(),
          expires_at timestamptz NOT NULL,
          last_seen_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE magic_links (
          id uuid PRIMARY KEY,
          token_hash bytea NOT NULL UNIQUE,
          email citext NOT NULL,
          expires_at timestamptz NOT NULL,
          used_at timestamptz
        );
        CREATE TABLE jobs (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL,
          kind text NOT NULL,
          payload jsonb NOT NULL DEFAULT '{}',
          status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','done','failed')),
          attempts int NOT NULL DEFAULT 0,
          run_after timestamptz NOT NULL DEFAULT now(),
          locked_at timestamptz,
          last_error text,
          created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX jobs_ready ON jobs (status, run_after);
        """
    )

    # ---- tenancy ----
    op.execute(
        f"""
        CREATE TABLE orgs (
          id uuid PRIMARY KEY,
          name text NOT NULL,
          country text NOT NULL DEFAULT 'US',
          currency text NOT NULL DEFAULT 'USD',
          timezone text NOT NULL DEFAULT 'America/New_York',
          created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE memberships (
          org_id uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
          user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          role text NOT NULL CHECK (role IN ('owner','admin','member','viewer')),
          created_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (org_id, user_id)
        );
        ALTER TABLE memberships ENABLE ROW LEVEL SECURITY;
        CREATE POLICY memberships_visible ON memberships
          USING (org_id = {ORG} OR user_id = {USR}) WITH CHECK (org_id = {ORG});

        ALTER TABLE orgs ENABLE ROW LEVEL SECURITY;
        CREATE POLICY orgs_visible ON orgs
          USING (id = {ORG} OR id IN (SELECT org_id FROM memberships WHERE user_id = {USR}))
          WITH CHECK (id = {ORG});

        CREATE TABLE invites (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
          email citext NOT NULL,
          role text NOT NULL CHECK (role IN ('admin','member','viewer')),
          token_hash bytea NOT NULL UNIQUE,
          invited_by uuid NOT NULL REFERENCES users(id),
          expires_at timestamptz NOT NULL,
          accepted_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now()
        );
        {tenant_rls("invites")}

        -- Accepting an invite happens before the user has a tenant context, so the token lookup
        -- runs as the owner through a narrow SECURITY DEFINER function, never as a broad grant.
        CREATE FUNCTION keel_find_invite(p_hash bytea)
          RETURNS TABLE (id uuid, org_id uuid, email citext, role text, expires_at timestamptz,
                         accepted_at timestamptz)
          LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
            SELECT id, org_id, email, role, expires_at, accepted_at FROM invites WHERE token_hash = p_hash
          $$;
        REVOKE ALL ON FUNCTION keel_find_invite(bytea) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION keel_find_invite(bytea) TO keel_app;

        CREATE TABLE tenant_profile (
          org_id uuid PRIMARY KEY REFERENCES orgs(id) ON DELETE CASCADE,
          profile jsonb NOT NULL DEFAULT '{{}}',
          updated_at timestamptz NOT NULL DEFAULT now()
        );
        {tenant_rls("tenant_profile")}

        CREATE TABLE audit_log (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL,
          actor_user_id uuid,
          action text NOT NULL,
          target_type text,
          target_id text,
          data jsonb NOT NULL DEFAULT '{{}}',
          at timestamptz NOT NULL DEFAULT now()
        );
        {tenant_rls("audit_log")}

        CREATE TABLE approvals (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL,
          gate text NOT NULL,
          payload_hash text NOT NULL,
          summary jsonb NOT NULL,
          staged_payload jsonb NOT NULL,
          status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','used')),
          requested_by uuid,
          decided_by uuid,
          decided_at timestamptz,
          used_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now()
        );
        {tenant_rls("approvals")}

        CREATE TABLE usage_events (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL,
          kind text NOT NULL,
          model text,
          input_tokens int NOT NULL DEFAULT 0,
          output_tokens int NOT NULL DEFAULT 0,
          pages int NOT NULL DEFAULT 0,
          cost_usd numeric(12,6) NOT NULL DEFAULT 0,
          ref jsonb NOT NULL DEFAULT '{{}}',
          at timestamptz NOT NULL DEFAULT now()
        );
        {tenant_rls("usage_events")}

        CREATE TABLE counters (
          org_id uuid NOT NULL,
          name text NOT NULL,
          value bigint NOT NULL DEFAULT 0,
          PRIMARY KEY (org_id, name)
        );
        {tenant_rls("counters")}
        """
    )
    op.execute(GRANTS)


def downgrade() -> None:
    op.execute(
        "DROP TABLE IF EXISTS counters, usage_events, approvals, audit_log, tenant_profile, invites, "
        "memberships, orgs, jobs, magic_links, sessions, users CASCADE; "
        "DROP FUNCTION IF EXISTS keel_find_invite(bytea);"
    )
