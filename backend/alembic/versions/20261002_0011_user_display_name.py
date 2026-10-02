"""Add an optional display name to users.

Revision ID: 20261002_0011
Revises: 20261002_0010
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261002_0011"
down_revision: str | None = "20261002_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("display_name", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "display_name")
