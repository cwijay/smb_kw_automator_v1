"""Helpers shared by migrations: one RLS policy shape for every tenant table."""

ORG = "NULLIF(current_setting('app.org_id', true), '')::uuid"
USR = "NULLIF(current_setting('app.user_id', true), '')::uuid"


def tenant_rls(table: str) -> str:
    return f"""
    ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
    CREATE POLICY {table}_tenant ON {table}
      USING (org_id = {ORG}) WITH CHECK (org_id = {ORG});
    """


# Regulatory records: the app role may only INSERT and SELECT them (a trigger also refuses UPDATE/DELETE).
APPEND_ONLY = ("batches", "batch_inputs", "haccp_readings", "corrective_actions")

GRANTS = (
    """
GRANT USAGE ON SCHEMA public TO keel_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO keel_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO keel_app;
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['"""
    + "','".join(APPEND_ONLY)
    + """'] LOOP
    IF to_regclass(t) IS NOT NULL THEN EXECUTE format('REVOKE UPDATE, DELETE ON %I FROM keel_app', t); END IF;
  END LOOP;
END $$;
"""
)
