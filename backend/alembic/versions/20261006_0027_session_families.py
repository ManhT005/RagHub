"""Add refresh-token session families.

Revision ID: 20261006_0027
Revises: 20261005_0026
"""

import sqlalchemy as sa

from alembic import op

revision = "20261006_0027"
down_revision = "20261005_0026"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("user_sessions")}
    if "family_id" not in columns:
        op.add_column("user_sessions", sa.Column("family_id", sa.Uuid(), nullable=True))
    op.execute("UPDATE user_sessions SET family_id = id WHERE family_id IS NULL")
    op.alter_column("user_sessions", "family_id", nullable=False)
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("user_sessions")}
    if "ix_user_sessions_family_id" not in indexes:
        op.create_index("ix_user_sessions_family_id", "user_sessions", ["family_id"])


def downgrade():
    op.drop_index("ix_user_sessions_family_id", table_name="user_sessions")
    op.drop_column("user_sessions", "family_id")
