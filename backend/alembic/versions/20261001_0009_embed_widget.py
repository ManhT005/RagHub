"""Add embeddable chatbot configuration.

Revision ID: 20261001_0009
Revises: 20260930_0008
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261001_0009"
down_revision: str | None = "20260930_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chatbots", sa.Column("embed_key_hash", sa.String(64)))
    op.add_column(
        "chatbots", sa.Column("allowed_origins", sa.JSON(), nullable=False, server_default="[]")
    )
    op.add_column(
        "chatbots",
        sa.Column("embed_primary_color", sa.String(16), nullable=False, server_default="#1463ff"),
    )
    op.add_column(
        "chatbots",
        sa.Column("embed_title", sa.String(120), nullable=False, server_default="RagHub Assistant"),
    )
    op.add_column(
        "chatbots",
        sa.Column(
            "embed_greeting",
            sa.Text(),
            nullable=False,
            server_default="Xin chao! Toi co the giup gi cho ban?",
        ),
    )
    op.create_index("ix_chatbots_embed_key_hash", "chatbots", ["embed_key_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_chatbots_embed_key_hash", table_name="chatbots")
    op.drop_column("chatbots", "embed_greeting")
    op.drop_column("chatbots", "embed_title")
    op.drop_column("chatbots", "embed_primary_color")
    op.drop_column("chatbots", "allowed_origins")
    op.drop_column("chatbots", "embed_key_hash")
