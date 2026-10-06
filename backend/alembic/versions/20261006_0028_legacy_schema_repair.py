"""Repair schema omitted by the legacy, colliding migration chain.

Revision ID: 20261006_0028
Revises: 20261006_0025
"""

import sqlalchemy as sa

from alembic import op

revision = "20261006_0028"
down_revision = "20261006_0025"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    workspace_columns = {column["name"] for column in inspector.get_columns("workspaces")}

    if "rerank_provider_id" not in workspace_columns:
        op.add_column("workspaces", sa.Column("rerank_provider_id", sa.Uuid(), nullable=True))
    if "rerank_config" not in workspace_columns:
        op.add_column(
            "workspaces",
            sa.Column("rerank_config", sa.JSON(), nullable=False, server_default="{}"),
        )

    inspector = sa.inspect(bind)
    foreign_keys = {key.get("name") for key in inspector.get_foreign_keys("workspaces")}
    if "fk_workspace_rerank_provider" not in foreign_keys:
        op.create_foreign_key(
            "fk_workspace_rerank_provider",
            "workspaces",
            "provider_configs",
            ["rerank_provider_id"],
            ["id"],
            ondelete="SET NULL",
        )
    indexes = {index["name"] for index in inspector.get_indexes("workspaces")}
    if "ix_workspaces_rerank_provider_id" not in indexes:
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


def downgrade():
    # This repair can run on both legacy and canonical schemas. Reversing it
    # could remove objects owned by earlier canonical migrations.
    pass
