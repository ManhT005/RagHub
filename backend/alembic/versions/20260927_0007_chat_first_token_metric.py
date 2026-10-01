"""Add first-token latency to chat usage events.

Revision ID: 20260927_0007
Revises: 20260925_0006
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260927_0007"
down_revision: str | None = "20260925_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("usage_events", sa.Column("first_token_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("usage_events", "first_token_ms")
