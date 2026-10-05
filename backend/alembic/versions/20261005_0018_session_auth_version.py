"""Bind refresh sessions to the password/auth policy version that issued them."""

import sqlalchemy as sa

from alembic import op

revision = "20261005_0018"
down_revision = "20261005_0017"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user_sessions",
        sa.Column("auth_version", sa.Integer(), nullable=False, server_default="0"),
    )
    # Preserve valid sessions on upgrade, even when the owner previously changed passwords.
    op.execute("""
        UPDATE user_sessions AS session SET auth_version = users.auth_version
        FROM users WHERE session.user_id = users.id
    """)


def downgrade():
    op.drop_column("user_sessions", "auth_version")
