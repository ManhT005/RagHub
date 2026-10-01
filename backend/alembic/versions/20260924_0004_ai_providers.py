"""Add organization AI providers and versioned embedding indexes.

Revision ID: 20260924_0004
Revises: 20260924_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260924_0004"
down_revision: str | None = "20260924_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("chatbots", "model", existing_type=sa.String(200), nullable=True)
    op.create_table(
        "provider_configs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("provider_type", sa.String(64), nullable=False),
        sa.Column("capability", sa.String(32), nullable=False),
        sa.Column("base_url", sa.String(1024)),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("dimension", sa.Integer()),
        sa.Column("encrypted_secret", sa.Text()),
        sa.Column("config_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "dimension IS NULL OR dimension > 0", name="ck_provider_dimension_positive"
        ),
    )
    op.create_index("ix_provider_configs_organization_id", "provider_configs", ["organization_id"])
    op.create_index(
        "ix_provider_configs_org_capability",
        "provider_configs",
        ["organization_id", "capability"],
    )

    op.add_column("workspaces", sa.Column("embedding_provider_id", sa.Uuid()))
    op.add_column("workspaces", sa.Column("chat_provider_id", sa.Uuid()))
    op.create_foreign_key(
        "fk_workspaces_embedding_provider",
        "workspaces",
        "provider_configs",
        ["embedding_provider_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_workspaces_chat_provider",
        "workspaces",
        "provider_configs",
        ["chat_provider_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_workspaces_embedding_provider_id", "workspaces", ["embedding_provider_id"])
    op.create_index("ix_workspaces_chat_provider_id", "workspaces", ["chat_provider_id"])

    op.create_table(
        "embedding_index_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "provider_config_id",
            sa.Uuid(),
            sa.ForeignKey("provider_configs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("dimension", sa.Integer(), nullable=False),
        sa.Column("embedding_fingerprint", sa.String(64), nullable=False),
        sa.Column("index_name", sa.String(255), nullable=False, unique=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="BUILDING"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("dimension > 0", name="ck_index_version_dimension_positive"),
    )
    op.create_index(
        "ix_embedding_index_versions_organization_id",
        "embedding_index_versions",
        ["organization_id"],
    )
    op.create_index(
        "ix_embedding_index_versions_workspace_id", "embedding_index_versions", ["workspace_id"]
    )
    op.create_index(
        "ix_embedding_index_versions_provider_config_id",
        "embedding_index_versions",
        ["provider_config_id"],
    )
    op.create_index(
        "ix_embedding_index_versions_embedding_fingerprint",
        "embedding_index_versions",
        ["embedding_fingerprint"],
    )
    op.create_index(
        "ix_embedding_index_versions_workspace_status",
        "embedding_index_versions",
        ["workspace_id", "status"],
    )
    op.add_column("workspaces", sa.Column("active_embedding_index_version_id", sa.Uuid()))
    op.create_foreign_key(
        "fk_workspaces_active_embedding_index_version",
        "workspaces",
        "embedding_index_versions",
        ["active_embedding_index_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_workspaces_active_embedding_index_version_id",
        "workspaces",
        ["active_embedding_index_version_id"],
    )

    op.create_table(
        "embedding_reindex_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_index_version_id",
            sa.Uuid(),
            sa.ForeignKey("embedding_index_versions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="QUEUED"),
        sa.Column("total_documents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_documents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_documents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_message", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_embedding_reindex_jobs_organization_id", "embedding_reindex_jobs", ["organization_id"]
    )
    op.create_index(
        "ix_embedding_reindex_jobs_workspace_id", "embedding_reindex_jobs", ["workspace_id"]
    )


def downgrade() -> None:
    op.drop_table("embedding_reindex_jobs")
    op.drop_index("ix_workspaces_active_embedding_index_version_id", table_name="workspaces")
    op.drop_constraint(
        "fk_workspaces_active_embedding_index_version", "workspaces", type_="foreignkey"
    )
    op.drop_column("workspaces", "active_embedding_index_version_id")
    op.drop_table("embedding_index_versions")
    op.drop_index("ix_workspaces_chat_provider_id", table_name="workspaces")
    op.drop_index("ix_workspaces_embedding_provider_id", table_name="workspaces")
    op.drop_constraint("fk_workspaces_chat_provider", "workspaces", type_="foreignkey")
    op.drop_constraint("fk_workspaces_embedding_provider", "workspaces", type_="foreignkey")
    op.drop_column("workspaces", "chat_provider_id")
    op.drop_column("workspaces", "embedding_provider_id")
    op.drop_table("provider_configs")
    op.execute("UPDATE chatbots SET model = 'gemini-2.5-flash' WHERE model IS NULL")
    op.alter_column("chatbots", "model", existing_type=sa.String(200), nullable=False)
