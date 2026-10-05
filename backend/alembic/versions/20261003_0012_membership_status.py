"""Scope organization access lifecycle to membership.

Revision ID: 20261003_0012
Revises: 20261002_0011
"""

import sqlalchemy as sa

from alembic import op

revision = "20261003_0012"
down_revision = "20261002_0011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "memberships", sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE")
    )
    op.create_check_constraint(
        "ck_memberships_status", "memberships", "status IN ('ACTIVE', 'DISABLED')"
    )
    # Preserve any existing global identity suspension; no accounts are silently reactivated.
    op.execute("""UPDATE memberships SET status = 'DISABLED'
                  WHERE user_id IN (SELECT id FROM users WHERE status = 'DISABLED')""")


def downgrade():
    op.drop_constraint("ck_memberships_status", "memberships", type_="check")
    op.drop_column("memberships", "status")
