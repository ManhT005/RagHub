"""Persist Ollama pull progress across API and worker restarts."""

import sqlalchemy as sa

from alembic import op

revision = "20261005_0020"
down_revision = "20261005_0019"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ollama_model_pulls",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "connection_id",
            sa.Uuid(),
            sa.ForeignKey("provider_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("register_after_pull", sa.Boolean(), nullable=False),
        sa.Column("completed_bytes", sa.BigInteger(), nullable=False),
        sa.Column("total_bytes", sa.BigInteger(), nullable=False),
        sa.Column("error_code", sa.String(100)),
        sa.Column(
            "registered_model_id",
            sa.Uuid(),
            sa.ForeignKey("provider_configs.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_ollama_model_pulls_organization_id", "ollama_model_pulls", ["organization_id"]
    )
    op.create_index("ix_ollama_model_pulls_connection_id", "ollama_model_pulls", ["connection_id"])
    op.create_index(
        "ix_ollama_pull_active_connection",
        "ollama_model_pulls",
        ["connection_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('QUEUED', 'PULLING', 'VERIFYING')"),
    )


def downgrade():
    op.drop_table("ollama_model_pulls")
