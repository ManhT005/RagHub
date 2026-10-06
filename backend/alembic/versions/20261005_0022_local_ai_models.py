"""Track curated local model downloads without activating embedding runtime."""

import sqlalchemy as sa

from alembic import op

revision = "20261005_0022"
down_revision = "20261005_0021"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "local_ai_models",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("catalog_id", sa.String(100), nullable=False),
        sa.Column("revision", sa.String(40), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("completed_bytes", sa.BigInteger(), nullable=False),
        sa.Column("total_bytes", sa.BigInteger(), nullable=False),
        sa.Column("error_code", sa.String(100)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("organization_id", "catalog_id", name="uq_local_ai_org_catalog"),
    )
    op.create_index("ix_local_ai_models_organization_id", "local_ai_models", ["organization_id"])


def downgrade():
    op.drop_table("local_ai_models")
