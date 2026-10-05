"""Persistent AI defaults without binding a nonexistent setup workspace."""

import sqlalchemy as sa

from alembic import op

revision = "20261005_0019"
down_revision = "20261005_0018"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "organization_ai_defaults",
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "default_embedding_model_id",
            sa.Uuid(),
            sa.ForeignKey("provider_configs.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "default_chat_model_id",
            sa.Uuid(),
            sa.ForeignKey("provider_configs.id", ondelete="SET NULL"),
        ),
    )


def downgrade():
    op.drop_table("organization_ai_defaults")
