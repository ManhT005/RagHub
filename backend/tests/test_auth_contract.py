from app.main import app


def test_auth_openapi_exposes_internal_account_contract_only() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/auth/register" not in paths
    assert "/api/v1/auth/email/verify" not in paths
    assert "/api/v1/auth/email/resend" not in paths
    assert "/api/v1/auth/google" not in paths
    assert "/api/v1/auth/providers" not in paths
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/password/forgot" in paths
    assert "/api/v1/auth/password/reset" in paths
    assert "/api/v1/auth/password/change" in paths
