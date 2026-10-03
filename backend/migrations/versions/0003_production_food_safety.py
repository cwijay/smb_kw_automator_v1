"""Production and food safety: formulas, lots, batches, HACCP readings, allocations.

Batches and HACCP readings are append-only at the database level: the app role cannot UPDATE or DELETE
them, and a trigger refuses it for everyone else. A correction is a new version that supersedes the old.

Revision ID: 0003
"""

from alembic import op

from migrations.rls import APPEND_ONLY, GRANTS, tenant_rls

revision = "0003"
down_revision = "0002"

TENANT_TABLES = [
    "formulas",
    "lots",
    "batches",
    "batch_inputs",
    "ccp_definitions",
    "haccp_readings",
    "corrective_actions",
    "allocations",
]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE formulas (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
          product_id uuid NOT NULL REFERENCES products(id),
          batch_size numeric(12,3) NOT NULL,
          unit text NOT NULL,
          items jsonb NOT NULL DEFAULT '[]',
          version int NOT NULL DEFAULT 1,
          created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE lots (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
          code text NOT NULL,
          kind text NOT NULL CHECK (kind IN ('ingredient','product')),
          product_id uuid REFERENCES products(id),
          ingredient text,
          supplier text,
          quantity numeric(12,3),
          unit text,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (org_id, code)
        );
        CREATE TABLE batches (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
          number text NOT NULL,
          product_id uuid REFERENCES products(id),
          output_lot_id uuid REFERENCES lots(id),
          made_on date,
          quantity numeric(12,3),
          unit text,
          prepared_by text,
          source_document_id uuid REFERENCES documents(id),
          approval_id uuid,
          signed_off_by uuid,
          version int NOT NULL DEFAULT 1,
          supersedes uuid REFERENCES batches(id),
          created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE batch_inputs (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL,
          batch_id uuid NOT NULL REFERENCES batches(id),
          lot_id uuid REFERENCES lots(id),
          ingredient text NOT NULL,
          quantity numeric(12,3),
          unit text,
          status text NOT NULL CHECK (status IN ('read','missing'))
        );
        CREATE TABLE ccp_definitions (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
          name text NOT NULL,
          min_value numeric(12,3),
          max_value numeric(12,3),
          unit text NOT NULL,
          aliases text[] NOT NULL DEFAULT '{}',
          active boolean NOT NULL DEFAULT true,
          created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE haccp_readings (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL,
          ccp_id uuid REFERENCES ccp_definitions(id),
          ccp_as_written text NOT NULL,
          batch_number text,
          value numeric(12,3),
          unit text,
          status text NOT NULL CHECK (status IN ('read','missing','out_of_range')),
          recorded_on date,
          recorded_at_time text,
          operator text,
          source_document_id uuid REFERENCES documents(id),
          approval_id uuid,
          verified_by uuid,
          version int NOT NULL DEFAULT 1,
          supersedes uuid REFERENCES haccp_readings(id),
          created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE corrective_actions (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL,
          reading_id uuid NOT NULL REFERENCES haccp_readings(id),
          action text NOT NULL,
          recorded_by uuid,
          created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE allocations (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL,
          order_line_id uuid NOT NULL REFERENCES order_lines(id) ON DELETE CASCADE,
          lot_id uuid NOT NULL REFERENCES lots(id),
          quantity numeric(12,3),
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (order_line_id, lot_id)
        );

        CREATE FUNCTION keel_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION '% is append-only: record a new version instead', TG_TABLE_NAME;
        END $$;
        """
    )
    op.execute("".join(tenant_rls(t) for t in TENANT_TABLES))
    for t in APPEND_ONLY:
        op.execute(
            f"CREATE TRIGGER {t}_append_only BEFORE UPDATE OR DELETE ON {t} "
            f"FOR EACH ROW EXECUTE FUNCTION keel_append_only();"
        )
    op.execute(GRANTS)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS " + ", ".join(reversed(TENANT_TABLES)) + " CASCADE;")
    op.execute("DROP FUNCTION IF EXISTS keel_append_only();")
