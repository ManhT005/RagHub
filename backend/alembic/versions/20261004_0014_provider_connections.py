"""Separate connection credentials from stable runtime model registration IDs."""

import uuid

import sqlalchemy as sa

from alembic import op

revision = "20261004_0014"
down_revision = "20261004_0013"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "provider_connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("provider_type", sa.String(64), nullable=False),
        sa.Column("base_url", sa.String(1024)),
        sa.Column("encrypted_secret", sa.Text()),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="UNTESTED"),
        sa.Column("last_tested_at", sa.DateTime(timezone=True)),
        sa.Column("last_latency_ms", sa.Integer()),
        sa.Column("last_error_code", sa.String(100)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_provider_connections_organization_id", "provider_connections", ["organization_id"]
    )
    op.add_column(
        "provider_configs",
        sa.Column(
            "connection_id",
            sa.Uuid(),
            sa.ForeignKey("provider_connections.id", ondelete="RESTRICT"),
        ),
    )
    op.create_index("ix_provider_configs_connection_id", "provider_configs", ["connection_id"])
    op.add_column("provider_configs", sa.Column("display_name", sa.String(200)))
    op.add_column(
        "provider_configs",
        sa.Column("availability_status", sa.String(32), nullable=False, server_default="UNTESTED"),
    )
    op.add_column(
        "provider_configs",
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column("provider_configs", sa.Column("last_health_check_at", sa.DateTime(timezone=True)))
    bind = op.get_bind()
    models = sa.Table("provider_configs", sa.MetaData(), autoload_with=bind)
    connections = sa.Table("provider_connections", sa.MetaData(), autoload_with=bind)
    for row in bind.execute(sa.select(models)).mappings():
        connection_id = uuid.uuid4()
        bind.execute(
            connections.insert().values(
                id=connection_id,
                organization_id=row["organization_id"],
                name=row["name"],
                provider_type=row["provider_type"],
                base_url=row["base_url"],
                encrypted_secret=row["encrypted_secret"],
                config_json=row["config_json"],
                enabled=row["enabled"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        )
        bind.execute(
            models.update()
            .where(models.c.id == row["id"])
            .values(
                connection_id=connection_id,
                display_name=row["name"],
                encrypted_secret=None,
            )
        )


def downgrade():
    # Restore runtime credentials before removing connections, including newly registered models.
    op.execute("""UPDATE provider_configs p SET encrypted_secret = c.encrypted_secret
                  FROM provider_connections c WHERE p.connection_id = c.id""")
    for column in ("last_health_check_at", "metadata_json", "availability_status", "display_name"):
        op.drop_column("provider_configs", column)
    op.drop_index("ix_provider_configs_connection_id", table_name="provider_configs")
    op.drop_column("provider_configs", "connection_id")
    op.drop_table("provider_connections")
