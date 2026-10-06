"""Singleton installation state; existing data never reopens public setup."""

from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision = "20261005_0017"
down_revision = "20261004_0016"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "installation_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("installation_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column(
            "organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="SET NULL")
        ),
        sa.Column("initialized_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("id = 1", name="ck_installation_singleton"),
        sa.CheckConstraint(
            "status IN ('UNINITIALIZED', 'INITIALIZING', 'INITIALIZED')",
            name="ck_installation_status",
        ),
    )
    # Conservatively protect any existing installation, including suspended/deleted owners.
    op.execute(
        sa.text("""
        INSERT INTO installation_state
            (id, status, installation_id, initialized_at, owner_id, organization_id)
        SELECT 1,
            CASE WHEN EXISTS (SELECT 1 FROM users) OR EXISTS (SELECT 1 FROM organizations)
                 THEN 'INITIALIZED' ELSE 'UNINITIALIZED' END,
            CAST(:installation_id AS uuid),
            CASE WHEN EXISTS (SELECT 1 FROM users) OR EXISTS (SELECT 1 FROM organizations)
                 THEN now() ELSE NULL END,
            (SELECT user_id FROM memberships WHERE role = 'ADMIN'
                ORDER BY organization_id, user_id LIMIT 1),
            (SELECT organization_id FROM memberships WHERE role = 'ADMIN'
                ORDER BY organization_id, user_id LIMIT 1)
    """).bindparams(installation_id=str(uuid4()))
    )


def downgrade():
    op.drop_table("installation_state")
