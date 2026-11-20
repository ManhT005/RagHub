"""Add public widget logo display preferences.

Revision ID: 20261009_0034
Revises: 20261007_0033
"""

import sqlalchemy as sa
from alembic import op

revision = "20261009_0034"
down_revision = "20261007_0033"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("chatbots", sa.Column("embed_logo_shape", sa.String(16), nullable=False, server_default="rounded"))
    op.add_column("chatbots", sa.Column("embed_logo_fit", sa.String(16), nullable=False, server_default="contain"))


def downgrade():
    op.drop_column("chatbots", "embed_logo_fit")
    op.drop_column("chatbots", "embed_logo_shape")
