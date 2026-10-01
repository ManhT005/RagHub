from app.core.exceptions import AppError


class ProviderError(AppError):
    def __init__(self, code: str, message: str, *, status_code: int = 502) -> None:
        super().__init__(code, message, status_code=status_code)


class ProviderTimeoutError(ProviderError):
    def __init__(self, message: str = "The AI provider timed out.") -> None:
        super().__init__("PROVIDER_TIMEOUT", message, status_code=504)


class ProviderUnavailableError(ProviderError):
    def __init__(self, message: str = "The AI provider is unavailable.") -> None:
        super().__init__("PROVIDER_UNAVAILABLE", message)


class ProviderAuthenticationError(ProviderError):
    def __init__(self, message: str = "The AI provider rejected its credentials.") -> None:
        super().__init__("PROVIDER_AUTH_FAILED", message)


class ProviderRateLimitError(ProviderError):
    def __init__(self, message: str = "The AI provider rate limit was reached.") -> None:
        super().__init__("PROVIDER_RATE_LIMITED", message)


class ProviderInvalidResponseError(ProviderError):
    def __init__(self, message: str = "The AI provider returned an invalid response.") -> None:
        super().__init__("PROVIDER_INVALID_RESPONSE", message)


class ProviderConfigurationError(ProviderError):
    def __init__(
        self,
        message: str = "The AI provider is not configured.",
        *,
        code: str = "PROVIDER_NOT_CONFIGURED",
        status_code: int = 422,
    ) -> None:
        super().__init__(code, message, status_code=status_code)


class ProviderDisabledError(ProviderConfigurationError):
    def __init__(self) -> None:
        super().__init__("The AI provider is disabled.", code="PROVIDER_DISABLED", status_code=409)
