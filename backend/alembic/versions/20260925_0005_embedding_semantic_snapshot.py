"""Snapshot semantic embedding provider configuration.

Revision ID: 20260925_0005
Revises: 20260924_0004
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260925_0005"
down_revision: str | None = "20260924_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("embedding_index_versions", sa.Column("provider_type", sa.String(64)))
    op.add_column("embedding_index_versions", sa.Column("base_url", sa.String(1024)))
    op.add_column("embedding_index_versions", sa.Column("config_json", sa.JSON()))
    op.execute(
        """
        UPDATE embedding_index_versions AS version
        SET provider_type = config.provider_type,
            base_url = config.base_url,
            config_json = config.config_json
        FROM provider_configs AS config
        WHERE config.id = version.provider_config_id
        """
    )
    op.alter_column("embedding_index_versions", "provider_type", nullable=False)
    op.alter_column("embedding_index_versions", "config_json", nullable=False)


def downgrade() -> None:
    op.drop_column("embedding_index_versions", "config_json")
    op.drop_column("embedding_index_versions", "base_url")
    op.drop_column("embedding_index_versions", "provider_type")
