"""Keep the previously deployed session-family revision addressable.

Revision ID: 20261006_0025
Revises: 20261006_0027
"""

revision = "20261006_0025"
down_revision = "20261006_0027"
branch_labels = None
depends_on = None


def upgrade():
    # Deployments stamped with this legacy revision already contain the
    # provider-pool, ingestion, GC, clarification, and session-family schema.
    pass


def downgrade():
    pass
