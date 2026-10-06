"""Persist canonical work-item embedding identity for every provider."""
import sqlalchemy as sa

from alembic import op

revision = "20261006_0026"
down_revision = "20261006_0025"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("embedding_work_items", "pool_id", nullable=True)
    op.add_column("embedding_work_items", sa.Column("embedding_fingerprint", sa.String(64)))
    op.add_column("embedding_work_items", sa.Column("index_name", sa.String(255)))
    op.add_column("embedding_work_items", sa.Column("dimension", sa.Integer()))


def downgrade():
    # Local/non-pool jobs cannot be represented by the old schema.
    op.execute("DELETE FROM embedding_work_items WHERE pool_id IS NULL")
    for column in ("dimension", "index_name", "embedding_fingerprint"):
        op.drop_column("embedding_work_items", column)
    op.alter_column("embedding_work_items", "pool_id", nullable=False)
