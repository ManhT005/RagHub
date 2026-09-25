"""Track the current pending embedding index target.

Revision ID: 20260925_0006
Revises: 20260925_0005
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260925_0006"
down_revision: str | None = "20260925_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("workspaces", sa.Column("pending_embedding_index_version_id", sa.Uuid()))
    op.create_foreign_key(
        "fk_workspaces_pending_embedding_index_version",
        "workspaces",
        "embedding_index_versions",
        ["pending_embedding_index_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_workspaces_pending_embedding_index_version_id",
        "workspaces",
        ["pending_embedding_index_version_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_workspaces_pending_embedding_index_version_id", table_name="workspaces")
    op.drop_constraint(
        "fk_workspaces_pending_embedding_index_version", "workspaces", type_="foreignkey"
    )
    op.drop_column("workspaces", "pending_embedding_index_version_id")
