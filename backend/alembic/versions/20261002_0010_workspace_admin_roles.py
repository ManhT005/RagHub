"""Replace organization RBAC with admin and workspace admin roles.

Revision ID: 20261002_0010
Revises: 20261001_0009
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261002_0010"
down_revision: str | None = "20261001_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspace_memberships",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "workspace_id"),
    )
    op.execute(
        """
        INSERT INTO workspace_memberships (user_id, workspace_id)
        SELECT m.user_id, w.id
        FROM memberships AS m
        JOIN workspaces AS w ON w.organization_id = m.organization_id
        WHERE m.role IN ('EDITOR', 'VIEWER')
        """
    )
    op.execute(
        """
        UPDATE memberships
        SET role = CASE
            WHEN role IN ('OWNER', 'ADMIN') THEN 'ADMIN'
            ELSE 'WORKSPACE_ADMIN'
        END
        """
    )
    op.alter_column("memberships", "role", server_default="ADMIN")


def downgrade() -> None:
    op.execute(
        "UPDATE memberships SET role = CASE WHEN role = 'ADMIN' THEN 'ADMIN' ELSE 'EDITOR' END"
    )
    op.alter_column("memberships", "role", server_default="OWNER")
    op.drop_table("workspace_memberships")
