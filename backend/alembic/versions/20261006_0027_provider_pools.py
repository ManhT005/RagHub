"""Add managed provider pools with idempotent legacy backfill.

Revision ID: 20261006_0027
Revises: 20261005_0022
"""

import sqlalchemy as sa

from alembic import op

revision = "20261006_0027"
down_revision = "20261005_0022"
branch_labels = None
depends_on = None

# Backfill copies ciphertext verbatim (never decrypt/re-encrypt) and derives
# deterministic pool IDs from the legacy config ID, so re-running the
# migration cannot duplicate pools or credentials.
BACKFILL_POOLS_SQL = """
INSERT INTO provider_pools
    (id, organization_id, provider_type, capability, model, dimension,
     task_type, embedding_options, quota_scope, fingerprint_v2)
SELECT md5('pool:' || id::text)::uuid,
       organization_id, provider_type, capability, model, dimension,
       config_json ->> 'task_type',
       COALESCE(config_json, '{}'),
       provider_type || ':' || model || ':'
           || COALESCE(LOWER(COALESCE(config_json ->> 'quota_project',
                                      config_json ->> 'project_id', 'default')), 'default'),
       md5('fp:' || provider_type || '|' || COALESCE(base_url, '')
           || '|' || model || '|' || COALESCE(dimension::text, ''))::text
FROM provider_configs
ON CONFLICT (id) DO NOTHING
"""

BACKFILL_CREDENTIALS_SQL = """
INSERT INTO provider_credentials (id, pool_id, name, encrypted_secret, enabled)
SELECT md5('cred:' || id::text)::uuid,
       md5('pool:' || id::text)::uuid,
       'primary', encrypted_secret, enabled
FROM provider_configs
ON CONFLICT (id) DO NOTHING
"""


def upgrade():
    # Pre-merge RAG databases used develop's 0021/0022 IDs for these tables.
    # Detect already applied schema without recreating tables or touching data.
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("provider_pools"):
        if not inspector.has_table("provider_credentials"):
            raise RuntimeError("Incomplete legacy embedding schema; restore before upgrading.")
        return

    op.create_table(
        "provider_pools",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("provider_type", sa.String(64), nullable=False),
        sa.Column("capability", sa.String(32), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("dimension", sa.Integer(), nullable=True),
        sa.Column("task_type", sa.String(64), nullable=True),
        sa.Column("embedding_options", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("quota_scope", sa.String(255), nullable=False, server_default="default"),
        sa.Column("fingerprint_v2", sa.String(64), nullable=False, index=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Index("ix_provider_pools_org_fingerprint", "organization_id", "fingerprint_v2"),
    )
    op.create_table(
        "provider_credentials",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "pool_id",
            sa.Uuid(),
            sa.ForeignKey("provider_pools.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(200), nullable=False, server_default="primary"),
        sa.Column("encrypted_secret", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("unhealthy", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_table(
        "workspace_provider_bindings",
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
        sa.Column("capability", sa.String(32), nullable=False),
        sa.Column(
            "pool_id",
            sa.Uuid(),
            sa.ForeignKey("provider_pools.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("workspace_id", "capability", name="uq_workspace_bindings_ws_cap"),
    )
    op.add_column(
        "embedding_index_versions",
        sa.Column("embedding_fingerprint_v2", sa.String(64), nullable=True),
    )
    op.add_column(
        "embedding_index_versions",
        sa.Column("fingerprint_version", sa.String(8), nullable=False, server_default="v1"),
    )
    op.create_index(
        "ix_embedding_index_versions_embedding_fingerprint_v2",
        "embedding_index_versions",
        ["embedding_fingerprint_v2"],
    )
    op.execute(BACKFILL_POOLS_SQL)
    op.execute(BACKFILL_CREDENTIALS_SQL)
    # Bindings mirror legacy workspace columns; legacy columns stay for rollback.
    op.execute("""
INSERT INTO workspace_provider_bindings
    (id, organization_id, workspace_id, capability, pool_id)
SELECT md5('bind-emb:' || w.id::text)::uuid, w.organization_id, w.id,
       'EMBEDDING', md5('pool:' || w.embedding_provider_id::text)::uuid
FROM workspaces w
WHERE w.embedding_provider_id IS NOT NULL AND w.deleted_at IS NULL
ON CONFLICT DO NOTHING
""")
    op.execute("""
INSERT INTO workspace_provider_bindings
    (id, organization_id, workspace_id, capability, pool_id)
SELECT md5('bind-chat:' || w.id::text)::uuid, w.organization_id, w.id,
       'CHAT', md5('pool:' || w.chat_provider_id::text)::uuid
FROM workspaces w
WHERE w.chat_provider_id IS NOT NULL AND w.deleted_at IS NULL
ON CONFLICT DO NOTHING
""")


def downgrade():
    op.drop_index(
        "ix_embedding_index_versions_embedding_fingerprint_v2",
        table_name="embedding_index_versions",
    )
    op.drop_column("embedding_index_versions", "fingerprint_version")
    op.drop_column("embedding_index_versions", "embedding_fingerprint_v2")
    op.drop_table("workspace_provider_bindings")
    op.drop_table("provider_credentials")
    op.drop_table("provider_pools")
