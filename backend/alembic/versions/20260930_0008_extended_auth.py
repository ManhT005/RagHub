"""Add extensible identities, reset tokens, and refresh sessions.

Revision ID: 20260930_0008
Revises: 20260927_0007
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260930_0008"
down_revision: str | None = "20260927_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True)))
    op.add_column(
        "users", sa.Column("auth_version", sa.Integer(), server_default="0", nullable=False)
    )

    op.create_table(
        "user_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_subject", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(512)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "provider_subject", name="uq_user_identities_provider_subject"
        ),
        sa.UniqueConstraint("user_id", "provider", name="uq_user_identities_user_provider"),
    )
    op.create_index("ix_user_identities_user_id", "user_identities", ["user_id"])

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])
    op.create_index("ix_password_reset_tokens_expires_at", "password_reset_tokens", ["expires_at"])

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("refresh_token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("replaced_by_id", sa.Uuid()),
        sa.Column("user_agent", sa.String(512)),
        sa.Column("ip_address", sa.String(64)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["replaced_by_id"], ["user_sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("refresh_token_hash"),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"])

    connection = op.get_bind()
    users = connection.execute(
        sa.text("SELECT id, email, password_hash, created_at FROM users")
    ).mappings()
    for user in users:
        connection.execute(
            sa.text(
                """
                INSERT INTO user_identities
                    (id, user_id, provider, provider_subject, password_hash, created_at)
                VALUES
                    (:id, :user_id, 'LOCAL', :email, :password_hash, :created_at)
                """
            ),
            {
                "id": uuid.uuid4(),
                "user_id": user["id"],
                "email": user["email"].lower(),
                "password_hash": user["password_hash"],
                "created_at": user["created_at"],
            },
        )
    connection.execute(
        sa.text("UPDATE users SET email = lower(email), email_verified_at = created_at")
    )

    op.drop_constraint("users_email_key", "users", type_="unique")
    op.create_index("uq_users_email_lower", "users", [sa.text("lower(email)")], unique=True)
    op.create_check_constraint(
        "ck_users_status",
        "users",
        "status IN ('PENDING_VERIFICATION', 'ACTIVE', 'SUSPENDED', 'DISABLED')",
    )
    op.drop_column("users", "password_hash")


def downgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(512)))
    op.execute(
        """
        UPDATE users
        SET password_hash = identities.password_hash
        FROM user_identities AS identities
        WHERE identities.user_id = users.id AND identities.provider = 'LOCAL'
        """
    )
    op.alter_column("users", "password_hash", nullable=False)
    op.drop_constraint("ck_users_status", "users", type_="check")
    op.drop_index("uq_users_email_lower", table_name="users")
    op.create_unique_constraint("users_email_key", "users", ["email"])
    op.drop_table("user_sessions")
    op.drop_table("password_reset_tokens")
    op.drop_table("user_identities")
    op.drop_column("users", "auth_version")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "email_verified_at")
