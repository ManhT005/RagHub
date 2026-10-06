"""Use generic policy for new chatbots, preserving existing profile choices."""
from alembic import op

revision = "20261006_0025"
down_revision = "20261005_0024"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("chatbots", "domain_profile", server_default="generic")


def downgrade():
    op.alter_column("chatbots", "domain_profile", server_default="admissions")
