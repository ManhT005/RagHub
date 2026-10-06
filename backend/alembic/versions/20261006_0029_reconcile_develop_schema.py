"""Repair upstream schema for pre-merge RAG databases with overlapping revision IDs.

Develop owns 0021/0022. The RAG pool and work-item migrations now have unique IDs.
Existing RAG databases may already be stamped at 0023-0026 and therefore skip
those upstream ancestors; ensure the missing upstream structures at a new head.
"""

import importlib.util
from pathlib import Path

import sqlalchemy as sa

from alembic import op

revision = "20261006_0029"
down_revision = "20261006_0026"
branch_labels = None
depends_on = None


def _upstream_upgrade(filename):
    spec = importlib.util.spec_from_file_location(
        "upstream_schema", Path(__file__).with_name(filename)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.upgrade()


def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {c["name"] for c in inspector.get_columns("workspaces")}
    if not {"rerank_provider_id", "rerank_config"} <= columns:
        if {"rerank_provider_id", "rerank_config"} & columns:
            raise RuntimeError("Incomplete workspace rerank schema; restore before upgrading.")
        _upstream_upgrade("20261005_0021_workspace_rerank.py")
    if not inspector.has_table("local_ai_models"):
        _upstream_upgrade("20261005_0022_local_ai_models.py")


def downgrade():
    # Both structures are owned by upstream ancestors. Preserve their data here.
    pass
