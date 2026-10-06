import app.models  # noqa: F401
from app.core.database import Base


def test_auth_tables_are_registered_with_expected_columns() -> None:
    tables = Base.metadata.tables

    assert {
        "user_identities",
        "password_reset_tokens",
        "user_sessions",
    } <= set(tables)
    assert {
        "email_verified_at",
        "last_login_at",
        "auth_version",
    } <= {column.name for column in tables["users"].columns}
    assert {
        "provider",
        "provider_subject",
        "password_hash",
        "last_used_at",
    } <= {column.name for column in tables["user_identities"].columns}
    assert {
        "token_hash",
        "expires_at",
        "used_at",
    } <= {column.name for column in tables["password_reset_tokens"].columns}
    assert {
        "refresh_token_hash",
        "auth_version",
        "expires_at",
        "revoked_at",
        "replaced_by_id",
    } <= {column.name for column in tables["user_sessions"].columns}


def test_email_and_identity_constraints_are_present() -> None:
    tables = Base.metadata.tables
    user_indexes = {index.name for index in tables["users"].indexes}
    identity_constraints = {
        constraint.name for constraint in tables["user_identities"].constraints
    }

    assert "uq_users_email_lower" in user_indexes
    assert "uq_user_identities_provider_subject" in identity_constraints
    assert "uq_user_identities_user_provider" in identity_constraints
