"""Keep provider brand identity independent from its runtime adapter."""

import sqlalchemy as sa

from alembic import op

revision = "20261004_0016"
down_revision = "20261004_0015"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("provider_connections", sa.Column("catalog_id", sa.String(100), nullable=True))
    op.execute("""
        UPDATE provider_connections SET catalog_id = CASE
            WHEN provider_type = 'GOOGLE_GEMINI' THEN 'gemini'
            WHEN provider_type = 'OLLAMA' THEN 'ollama'
            WHEN provider_type = 'LOCAL_SENTENCE_TRANSFORMER' THEN 'sentence-transformer'
            WHEN provider_type = 'OPENAI_COMPATIBLE'
                AND rtrim(base_url, '/') = 'https://api.openai.com/v1' THEN 'openai'
            WHEN provider_type = 'OPENAI_COMPATIBLE' THEN 'compatible'
            ELSE NULL END
        WHERE catalog_id IS NULL
    """)


def downgrade():
    op.drop_column("provider_connections", "catalog_id")
