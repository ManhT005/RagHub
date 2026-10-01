import uuid

import pytest

from app.core.config import Settings
from app.core.security import (
    create_access_token,
    decode_token,
    generate_opaque_token,
    hash_otp,
    hash_token,
    verify_otp,
)


def test_access_token_carries_auth_version_and_session() -> None:
    settings = Settings(app_secret_key="test-secret")
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()

    encoded = create_access_token(
        user_id,
        settings,
        auth_version=4,
        session_id=session_id,
    )
    claims = decode_token(encoded, settings)

    assert claims.user_id == user_id
    assert claims.auth_version == 4
    assert claims.session_id == session_id
    assert claims.token_type == "access"


def test_opaque_tokens_are_random_and_only_need_a_stable_hash() -> None:
    first = generate_opaque_token()
    second = generate_opaque_token()

    assert first != second
    assert len(first) >= 40
    assert hash_token(first) == hash_token(first)
    assert hash_token(first) != hash_token(second)


def test_otp_hash_is_bound_to_email_and_secret() -> None:
    digest = hash_otp("User@Example.com", "123456", "app-secret")

    assert verify_otp("user@example.com", "123456", digest, "app-secret")
    assert not verify_otp("other@example.com", "123456", digest, "app-secret")
    assert not verify_otp("user@example.com", "654321", digest, "app-secret")


def test_decode_rejects_wrong_token_type() -> None:
    settings = Settings(app_secret_key="test-secret")
    encoded = create_access_token(uuid.uuid4(), settings, token_type="refresh")

    with pytest.raises(ValueError):
        decode_token(encoded, settings, expected_type="access")
