"""Add hashed access tokens for public conversations.

Revision ID: 20260930_0010
Revises: 20260930_0009
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260930_0010"
down_revision: str | None = "20260930_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations", sa.Column("public_access_token_hash", sa.String(64), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("conversations", "public_access_token_hash")
