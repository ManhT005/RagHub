"""Index GC audit trail: every dry-run/apply decision is recorded.

Revision ID: 20261005_0023
Revises: 20261005_0022
"""

import sqlalchemy as sa

from alembic import op

revision = "20261005_0023"
down_revision = "20261005_0022"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "index_gc_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("policy_version", sa.String(32), nullable=False, server_default="v1"),
        sa.Column("correlation_id", sa.String(128), nullable=True),
        sa.Column("candidates", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deletions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "index_gc_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Uuid(),
            sa.ForeignKey("index_gc_runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("index_name", sa.String(255), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=True),
        sa.Column("state", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("age_hours", sa.Float(), nullable=True),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(255), nullable=False, server_default=""),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_table("index_gc_items")
    op.drop_table("index_gc_runs")
