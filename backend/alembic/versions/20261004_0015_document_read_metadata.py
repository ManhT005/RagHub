"""Persist UI index metadata without coupling engine entities to the host."""

import sqlalchemy as sa

from alembic import op

revision = "20261004_0015"
down_revision = "20261004_0014"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("document_versions", sa.Column("chunk_count", sa.Integer()))
    op.add_column("document_versions", sa.Column("indexed_at", sa.DateTime(timezone=True)))
    op.create_table(
        "document_index_metadata",
        sa.Column(
            "document_version_id",
            sa.Uuid(),
            sa.ForeignKey("document_versions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "embedding_index_version_id",
            sa.Uuid(),
            sa.ForeignKey("embedding_index_versions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("document_index_metadata")
    op.drop_column("document_versions", "indexed_at")
    op.drop_column("document_versions", "chunk_count")
