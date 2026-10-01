import pytest

from app.modules.ai_providers.errors import (
    ProviderAuthenticationError,
    ProviderDisabledError,
    ProviderError,
    ProviderInvalidResponseError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)


@pytest.mark.parametrize(
    "error,status,code",
    [
        (ProviderTimeoutError(), 504, "PROVIDER_TIMEOUT"),
        (ProviderUnavailableError(), 502, "PROVIDER_UNAVAILABLE"),
        (ProviderAuthenticationError(), 502, "PROVIDER_AUTH_FAILED"),
        (ProviderRateLimitError(), 502, "PROVIDER_RATE_LIMITED"),
        (ProviderInvalidResponseError(), 502, "PROVIDER_INVALID_RESPONSE"),
        (ProviderDisabledError(), 409, "PROVIDER_DISABLED"),
    ],
)
def test_provider_errors_have_stable_http_mapping(
    error: ProviderError, status: int, code: str
) -> None:
    assert error.status_code == status
    assert error.code == code
