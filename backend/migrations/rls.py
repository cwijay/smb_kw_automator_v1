"""Helpers shared by migrations: one RLS policy shape for every tenant table."""

ORG = "NULLIF(current_setting('app.org_id', true), '')::uuid"
USR = "NULLIF(current_setting('app.user_id', true), '')::uuid"


def tenant_rls(table: str) -> str:
    return f"""
    ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
    CREATE POLICY {table}_tenant ON {table}
      USING (org_id = {ORG}) WITH CHECK (org_id = {ORG});
    """


GRANTS = """
GRANT USAGE ON SCHEMA public TO keel_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO keel_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO keel_app;
"""
