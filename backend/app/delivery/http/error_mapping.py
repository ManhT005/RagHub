from typing import Any

from raghub_core.domain.errors import CoreError

HTTP_STATUS_BY_CODE = {
    "DOCUMENT_NOT_FOUND": 404,
    "PUBLIC_CHAT_UNAVAILABLE": 503,
    "PUBLIC_CHAT_RATE_LIMITED": 429,
    "PUBLIC_CHAT_CONCURRENCY_LIMITED": 429,
    "WORKSPACE_NOT_FOUND": 404,
    "CHATBOT_NOT_FOUND": 404,
    "CONVERSATION_NOT_FOUND": 404,
    "CONVERSATION_ACCESS_DENIED": 403,
    "DOCUMENT_VERSION_NOT_FOUND": 404,
    "CHATBOT_NOT_PUBLISHED": 409,
    "INVALID_DOCUMENT_STATUS": 409,
    "DOCUMENT_NOT_RETRYABLE": 409,
    "INGESTION_IN_PROGRESS": 409,
    "UNSUPPORTED_FILE_TYPE": 400,
    "INVALID_CONTENT_TYPE": 400,
    "INVALID_PDF": 400,
    "EMPTY_FILE": 400,
    "INVALID_CHATBOT_CONFIG": 400,
    "FILE_TOO_LARGE": 413,
    "STORAGE_UNAVAILABLE": 503,
    "QUEUE_UNAVAILABLE": 503,
    "SEARCH_UNAVAILABLE": 503,
    "PROVIDER_TIMEOUT": 504,
    "PROVIDER_UNAVAILABLE": 502,
    "PROVIDER_AUTH_FAILED": 502,
    "PROVIDER_RATE_LIMITED": 502,
    "PROVIDER_INVALID_RESPONSE": 502,
    "EMBEDDING_DIMENSION_MISMATCH": 502,
    "PROVIDER_NOT_CONFIGURED": 422,
    "PROVIDER_DISABLED": 409,
    "CHAT_PROVIDER_NOT_CONFIGURED": 503,
}


class AppError(CoreError):
    """Compatibility error for existing HTTP/auth services with explicit statuses."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code, message, details=details)
        self.status_code = status_code


def http_status(error: CoreError) -> int:
    if isinstance(error, AppError):
        return error.status_code
    return HTTP_STATUS_BY_CODE.get(error.code, 500)
