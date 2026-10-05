"""Backfill explicit capabilities for existing delegated workspace assignments."""

import sqlalchemy as sa

from alembic import op

revision = "20261004_0013"
down_revision = "20261003_0012"
branch_labels = None
depends_on = None

# Freeze migration data independently of future application permission changes.
PERMISSIONS = (
    "workspace.view",
    "workspace.edit",
    "document.view",
    "document.upload",
    "document.reindex",
    "document.delete",
    "chat.use",
    "ai.view",
    "ai.change_embedding",
    "member.view",
    "member.manage",
)


def upgrade():
    op.create_table(
        "workspace_membership_permissions",
        sa.Column("user_id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), primary_key=True),
        sa.Column("permission", sa.String(64), primary_key=True),
        sa.ForeignKeyConstraint(
            ["user_id", "workspace_id"],
            ["workspace_memberships.user_id", "workspace_memberships.workspace_id"],
            ondelete="CASCADE",
        ),
    )
    for permission in PERMISSIONS:
        op.execute(
            sa.text("""
            INSERT INTO workspace_membership_permissions (user_id, workspace_id, permission)
            SELECT wm.user_id, wm.workspace_id, :permission
            FROM workspace_memberships wm
            JOIN workspaces w ON w.id = wm.workspace_id
            JOIN memberships m ON m.user_id = wm.user_id
              AND m.organization_id = w.organization_id
            WHERE m.role = 'WORKSPACE_ADMIN'
        """).bindparams(permission=permission)
        )


def downgrade():
    op.drop_table("workspace_membership_permissions")
