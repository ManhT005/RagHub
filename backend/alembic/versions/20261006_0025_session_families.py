"""Add refresh-token session families.

Revision ID: 20261006_0025
Revises: 20261005_0024
"""

import sqlalchemy as sa

from alembic import op

revision = "20261006_0025"
down_revision = "20261005_0024"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user_sessions", sa.Column("family_id", sa.Uuid(), nullable=True))
    op.execute("UPDATE user_sessions SET family_id = id WHERE family_id IS NULL")
    op.alter_column("user_sessions", "family_id", nullable=False)
    op.create_index("ix_user_sessions_family_id", "user_sessions", ["family_id"])


def downgrade():
    op.drop_index("ix_user_sessions_family_id", table_name="user_sessions")
    op.drop_column("user_sessions", "family_id")
