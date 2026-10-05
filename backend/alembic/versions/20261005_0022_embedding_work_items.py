"""Quota-aware resumable embedding work items and batch checkpoints.

Revision ID: 20261005_0022
Revises: 20261005_0021
"""

import sqlalchemy as sa

from alembic import op

revision = "20261005_0022"
down_revision = "20261005_0021"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "embedding_work_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "document_version_id",
            sa.Uuid(),
            sa.ForeignKey("document_versions.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "pool_id",
            sa.Uuid(),
            sa.ForeignKey("provider_pools.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False, server_default="upload"),
        sa.Column("state", sa.String(32), nullable=False, server_default="QUEUED", index=True),
        sa.Column("total_chunks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedded_chunks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("manifest_key", sa.String(1024), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Index("ix_embedding_work_items_ws_state", "workspace_id", "state"),
    )
    op.create_table(
        "embedding_batch_checkpoints",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "work_item_id",
            sa.Uuid(),
            sa.ForeignKey("embedding_work_items.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("batch_index", sa.Integer(), nullable=False),
        sa.Column("chunk_start", sa.Integer(), nullable=False),
        sa.Column("chunk_end", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("artifact_key", sa.String(1024), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "work_item_id", "batch_index", name="uq_batch_checkpoints_item_batch"
        ),
    )
    op.add_column("ingestion_jobs", sa.Column("embedded_chunks", sa.Integer(), nullable=True))
    op.add_column("ingestion_jobs", sa.Column("total_chunks", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("ingestion_jobs", "total_chunks")
    op.drop_column("ingestion_jobs", "embedded_chunks")
    op.drop_table("embedding_batch_checkpoints")
    op.drop_table("embedding_work_items")
