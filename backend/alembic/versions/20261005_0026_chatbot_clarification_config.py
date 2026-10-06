"""Chatbot clarification configuration.

Revision ID: 20261005_0026
Revises: 20261005_0025
"""

import sqlalchemy as sa

from alembic import op

revision = "20261005_0026"
down_revision = "20261005_0025"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Compatibility for databases that previously ran either side of the
    # duplicated 0021/0022 migration IDs before the branches were merged.
    workspace_columns = {column["name"] for column in inspector.get_columns("workspaces")}
    if "rerank_provider_id" not in workspace_columns:
        op.add_column("workspaces", sa.Column("rerank_provider_id", sa.Uuid(), nullable=True))
        op.add_column(
            "workspaces",
            sa.Column("rerank_config", sa.JSON(), nullable=False, server_default="{}"),
        )
        op.create_foreign_key(
            "fk_workspace_rerank_provider",
            "workspaces",
            "provider_configs",
            ["rerank_provider_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index("ix_workspaces_rerank_provider_id", "workspaces", ["rerank_provider_id"])

    if "local_ai_models" not in inspector.get_table_names():
        op.create_table(
            "local_ai_models",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "organization_id",
                sa.Uuid(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("catalog_id", sa.String(100), nullable=False),
            sa.Column("revision", sa.String(40), nullable=False),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("completed_bytes", sa.BigInteger(), nullable=False),
            sa.Column("total_bytes", sa.BigInteger(), nullable=False),
            sa.Column("error_code", sa.String(100)),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint("organization_id", "catalog_id", name="uq_local_ai_org_catalog"),
        )
        op.create_index(
            "ix_local_ai_models_organization_id", "local_ai_models", ["organization_id"]
        )

    chatbot_columns = {column["name"] for column in sa.inspect(bind).get_columns("chatbots")}
    if "clarification_mode" not in chatbot_columns:
        op.add_column(
            "chatbots",
            sa.Column(
                "clarification_mode",
                sa.String(32),
                nullable=False,
                server_default="conservative",
            ),
        )
    if "max_clarifying_turns" not in chatbot_columns:
        op.add_column(
            "chatbots",
            sa.Column("max_clarifying_turns", sa.Integer(), nullable=False, server_default="1"),
        )
    if "domain_profile" not in chatbot_columns:
        op.add_column(
            "chatbots",
            sa.Column("domain_profile", sa.String(64), nullable=False, server_default="admissions"),
        )


def downgrade():
    op.drop_column("chatbots", "domain_profile")
    op.drop_column("chatbots", "max_clarifying_turns")
    op.drop_column("chatbots", "clarification_mode")
