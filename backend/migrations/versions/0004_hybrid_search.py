"""Hybrid search: record which embedding model made each vector, and index vectors with HNSW.

Revision ID: 0004
"""

from alembic import op

revision = "0004"
down_revision = "0003"


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE chunks ADD COLUMN emb_model text;
        CREATE INDEX chunks_emb ON chunks USING hnsw (emb vector_cosine_ops);
        CREATE INDEX chunks_doc ON chunks (document_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX chunks_doc; DROP INDEX chunks_emb; ALTER TABLE chunks DROP COLUMN emb_model;")
