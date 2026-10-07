"""Store an optional logo for the public chatbot widget.

Revision ID: 20261007_0031
Revises: 20261006_0030
"""

import sqlalchemy as sa

from alembic import op

revision = "20261007_0031"
down_revision = "20261006_0030"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("chatbots", sa.Column("embed_logo_data", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("chatbots", "embed_logo_data")
