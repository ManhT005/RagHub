"""Optional workspace reranking, independent of embedding index versions."""

import sqlalchemy as sa

from alembic import op

revision = "20261005_0021"
down_revision = "20261005_0020"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("workspaces", sa.Column("rerank_provider_id", sa.Uuid(), nullable=True))
    op.add_column(
        "workspaces", sa.Column("rerank_config", sa.JSON(), nullable=False, server_default="{}")
    )
    op.create_foreign_key(
        "fk_workspace_rerank_provider",
        "workspaces",
        "provider_configs",
        ["rerank_provider_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_workspaces_rerank_provider_id", "workspaces", ["rerank_provider_id"])


def downgrade():
    op.drop_index("ix_workspaces_rerank_provider_id", table_name="workspaces")
    op.drop_constraint("fk_workspace_rerank_provider", "workspaces", type_="foreignkey")
    op.drop_column("workspaces", "rerank_config")
    op.drop_column("workspaces", "rerank_provider_id")
