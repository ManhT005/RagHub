"""Backfill public keys for already-published chatbots.

Revision ID: 20260930_0009
Revises: 20260929_0008
"""

import secrets
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260930_0009"
down_revision: str | None = "20260929_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    chatbot_ids = connection.execute(
        sa.text(
            "SELECT id FROM chatbots "
            "WHERE published = true AND public_key IS NULL FOR UPDATE"
        )
    ).scalars()
    for chatbot_id in chatbot_ids:
        public_key = "cb_pub_" + secrets.token_urlsafe(24)
        connection.execute(
            sa.text(
                "UPDATE chatbots SET public_key = :public_key "
                "WHERE id = :chatbot_id AND public_key IS NULL"
            ),
            {"chatbot_id": chatbot_id, "public_key": public_key},
        )


def downgrade() -> None:
    # Public identifiers may already be in use. Never invalidate them on downgrade.
    pass
