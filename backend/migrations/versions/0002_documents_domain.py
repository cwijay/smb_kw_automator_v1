"""Documents, extraction evidence, catalog, orders, invoices, workflow runs, search chunks.

Revision ID: 0002
"""

from alembic import op

from migrations.rls import GRANTS, tenant_rls

revision = "0002"
down_revision = "0001"

TENANT_TABLES = [
    "documents",
    "pages",
    "extractions",
    "field_results",
    "field_citations",
    "chunks",
    "customers",
    "products",
    "price_list",
    "orders",
    "order_lines",
    "invoices",
    "invoice_lines",
    "workflow_runs",
]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE documents (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
          kind text NOT NULL DEFAULT 'unknown',
          filename text NOT NULL,
          mime text NOT NULL,
          size_bytes int NOT NULL,
          sha256 text NOT NULL,
          storage_key text NOT NULL,
          source text NOT NULL DEFAULT 'upload',
          status text NOT NULL DEFAULT 'uploaded'
            CHECK (status IN ('uploaded','processing','needs_review','processed','failed')),
          page_count int NOT NULL DEFAULT 0,
          error text,
          created_by uuid,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (org_id, sha256)
        );
        CREATE TABLE pages (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL,
          document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
          n int NOT NULL,
          image_key text NOT NULL,
          width int NOT NULL,
          height int NOT NULL,
          has_text_layer boolean NOT NULL DEFAULT false,
          words jsonb NOT NULL DEFAULT '[]',
          UNIQUE (document_id, n)
        );
        CREATE TABLE extractions (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL,
          document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
          schema_name text NOT NULL,
          engine text NOT NULL,
          data jsonb NOT NULL,
          checks jsonb NOT NULL DEFAULT '[]',
          cost_usd numeric(12,6) NOT NULL DEFAULT 0,
          created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE field_results (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL,
          document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
          extraction_id uuid REFERENCES extractions(id) ON DELETE CASCADE,
          page_id uuid REFERENCES pages(id) ON DELETE CASCADE,
          path text NOT NULL,
          value jsonb,
          status text NOT NULL CHECK (status IN ('read','unreadable','blank','not_applicable','corrected')),
          confidence real NOT NULL DEFAULT 0,
          engine text NOT NULL,
          corrected_by uuid,
          corrected_at timestamptz,
          UNIQUE (extraction_id, path)
        );
        CREATE TABLE field_citations (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL,
          field_result_id uuid NOT NULL REFERENCES field_results(id) ON DELETE CASCADE,
          page_id uuid NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
          x real NOT NULL, y real NOT NULL, w real NOT NULL, h real NOT NULL,
          text text NOT NULL DEFAULT ''
        );
        CREATE TABLE chunks (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL,
          document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
          page_n int NOT NULL,
          text text NOT NULL,
          tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
          emb vector(512)
        );
        CREATE INDEX chunks_tsv ON chunks USING gin (tsv);

        CREATE TABLE customers (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
          name text NOT NULL,
          aliases text[] NOT NULL DEFAULT '{}',
          email text,
          address text,
          payment_terms_days int NOT NULL DEFAULT 30,
          created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX customers_name_trgm ON customers USING gin (name gin_trgm_ops);
        CREATE TABLE products (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
          sku text NOT NULL,
          name text NOT NULL,
          aliases text[] NOT NULL DEFAULT '{}',
          unit text NOT NULL DEFAULT 'each',
          unit_price numeric(12,2) NOT NULL DEFAULT 0,
          active boolean NOT NULL DEFAULT true,
          UNIQUE (org_id, sku)
        );
        CREATE INDEX products_name_trgm ON products USING gin (name gin_trgm_ops);
        CREATE TABLE price_list (
          org_id uuid NOT NULL,
          customer_id uuid NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
          product_id uuid NOT NULL REFERENCES products(id) ON DELETE CASCADE,
          unit_price numeric(12,2) NOT NULL,
          PRIMARY KEY (customer_id, product_id)
        );
        CREATE TABLE orders (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
          number text,
          customer_id uuid REFERENCES customers(id),
          customer_name_as_written text,
          order_date date,
          delivery_date date,
          status text NOT NULL DEFAULT 'approved' CHECK (status IN ('approved','invoiced','cancelled')),
          currency text NOT NULL,
          total numeric(12,2) NOT NULL DEFAULT 0,
          source_document_id uuid REFERENCES documents(id),
          approval_id uuid,
          created_by uuid,
          created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE order_lines (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL,
          order_id uuid NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
          product_id uuid REFERENCES products(id),
          description text NOT NULL,
          quantity numeric(12,3) NOT NULL,
          unit text NOT NULL DEFAULT 'each',
          unit_price numeric(12,2) NOT NULL,
          line_total numeric(12,2) NOT NULL
        );
        CREATE TABLE invoices (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
          number text NOT NULL,
          order_id uuid NOT NULL REFERENCES orders(id),
          customer_id uuid REFERENCES customers(id),
          issue_date date NOT NULL,
          due_date date NOT NULL,
          status text NOT NULL DEFAULT 'issued' CHECK (status IN ('issued','sent','exported','void')),
          currency text NOT NULL,
          subtotal numeric(12,2) NOT NULL,
          tax numeric(12,2) NOT NULL DEFAULT 0,
          total numeric(12,2) NOT NULL,
          approval_id uuid,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (org_id, number)
        );
        CREATE TABLE invoice_lines (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL,
          invoice_id uuid NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
          product_id uuid REFERENCES products(id),
          description text NOT NULL,
          quantity numeric(12,3) NOT NULL,
          unit_price numeric(12,2) NOT NULL,
          line_total numeric(12,2) NOT NULL
        );
        CREATE TABLE workflow_runs (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL,
          kind text NOT NULL,
          document_id uuid REFERENCES documents(id) ON DELETE CASCADE,
          status text NOT NULL DEFAULT 'running'
            CHECK (status IN ('running','waiting_approval','done','failed','cancelled')),
          pending_approval_id uuid,
          state jsonb NOT NULL DEFAULT '{}',
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("".join(tenant_rls(t) for t in TENANT_TABLES))
    op.execute(GRANTS)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS " + ", ".join(reversed(TENANT_TABLES)) + " CASCADE;")
