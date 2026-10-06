"""Chatbot clarification configuration.

Revision ID: 20261005_0024
Revises: 20261005_0023
"""

import sqlalchemy as sa

from alembic import op

revision = "20261005_0024"
down_revision = "20261005_0023"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "chatbots",
        sa.Column(
            "clarification_mode",
            sa.String(32),
            nullable=False,
            server_default="conservative",
        ),
    )
    op.add_column(
        "chatbots",
        sa.Column("max_clarifying_turns", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "chatbots",
        sa.Column("domain_profile", sa.String(64), nullable=False, server_default="admissions"),
    )


def downgrade():
    op.drop_column("chatbots", "domain_profile")
    op.drop_column("chatbots", "max_clarifying_turns")
    op.drop_column("chatbots", "clarification_mode")