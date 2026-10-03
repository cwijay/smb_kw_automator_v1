"""Batch corrections: a new version supersedes the old one and records why.

Revision ID: 0005
"""

from alembic import op

revision = "0005"
down_revision = "0004"


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE batches ADD COLUMN correction_reason text;
        CREATE UNIQUE INDEX batches_one_successor ON batches (supersedes) WHERE supersedes IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX batches_one_successor; ALTER TABLE batches DROP COLUMN correction_reason;")
