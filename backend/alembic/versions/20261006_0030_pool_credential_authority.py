"""Link managed credentials to connection-owned secrets without copying ciphertext."""

import sqlalchemy as sa

from alembic import op

revision = "20261006_0030"
down_revision = "20261006_0029"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("provider_credentials", sa.Column("provider_config_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_pool_credential_config",
        "provider_credentials",
        "provider_configs",
        ["provider_config_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_provider_credentials_provider_config_id", "provider_credentials", ["provider_config_id"]
    )
    # Deterministic legacy migration IDs identify the original credential authority.
    op.execute(
        sa.text("""
        UPDATE provider_credentials c
        SET provider_config_id = p.id,
            encrypted_secret = CASE WHEN p.connection_id IS NOT NULL
                THEN NULL ELSE c.encrypted_secret END
        FROM provider_configs p
        WHERE c.id = md5('cred:' || p.id::text)::uuid
    """)
    )


def downgrade():
    # Snapshot current DB-owned keys before removing the authority link.
    op.execute(
        sa.text("""
        UPDATE provider_credentials c SET encrypted_secret = co.encrypted_secret
        FROM provider_configs p JOIN provider_connections co ON co.id = p.connection_id
        WHERE c.provider_config_id = p.id
    """)
    )
    op.drop_index("ix_provider_credentials_provider_config_id", table_name="provider_credentials")
    op.drop_constraint("fk_pool_credential_config", "provider_credentials", type_="foreignkey")
    op.drop_column("provider_credentials", "provider_config_id")
