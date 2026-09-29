"""Add public chatbot access configuration.

Revision ID: 20260929_0008
Revises: 20260927_0007
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260929_0008"
down_revision: str | None = "20260927_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chatbots", sa.Column("public_key", sa.String(80), nullable=True))
    op.create_index("ix_chatbots_public_key", "chatbots", ["public_key"], unique=True)
    op.create_table(
        "chatbot_allowed_origins",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "chatbot_id",
            sa.Uuid(),
            sa.ForeignKey("chatbots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("origin", sa.String(512), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("chatbot_id", "origin"),
    )
    op.create_index(
        "ix_chatbot_allowed_origins_chatbot_id", "chatbot_allowed_origins", ["chatbot_id"]
    )
    op.create_table(
        "chatbot_api_keys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chatbot_id",
            sa.Uuid(),
            sa.ForeignKey("chatbots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("key_prefix", sa.String(24), nullable=False),
        sa.Column("key_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_chatbot_api_keys_organization_id", "chatbot_api_keys", ["organization_id"])
    op.create_index("ix_chatbot_api_keys_chatbot_id", "chatbot_api_keys", ["chatbot_id"])
    op.create_index("ix_chatbot_api_keys_key_prefix", "chatbot_api_keys", ["key_prefix"])


def downgrade() -> None:
    op.drop_index("ix_chatbot_api_keys_key_prefix", table_name="chatbot_api_keys")
    op.drop_index("ix_chatbot_api_keys_chatbot_id", table_name="chatbot_api_keys")
    op.drop_index("ix_chatbot_api_keys_organization_id", table_name="chatbot_api_keys")
    op.drop_table("chatbot_api_keys")
    op.drop_index("ix_chatbot_allowed_origins_chatbot_id", table_name="chatbot_allowed_origins")
    op.drop_table("chatbot_allowed_origins")
    op.drop_index("ix_chatbots_public_key", table_name="chatbots")
    op.drop_column("chatbots", "public_key")
