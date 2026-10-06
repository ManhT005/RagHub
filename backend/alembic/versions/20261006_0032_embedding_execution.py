"""Persist workspace execution preferences and immutable work-item batch layouts."""

import sqlalchemy as sa

from alembic import op

revision = "20261006_0032"
down_revision = "20261006_0031"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "workspaces",
        sa.Column("embedding_execution_config", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "embedding_work_items",
        sa.Column("execution_config", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade():
    op.drop_column("embedding_work_items", "execution_config")
    op.drop_column("workspaces", "embedding_execution_config")
