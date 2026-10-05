import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from raghub_core.domain.errors import CoreError

from app.delivery.http.error_mapping import AppError as AppError
from app.delivery.http.error_mapping import http_status

logger = logging.getLogger(__name__)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | list[Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": _request_id(request),
                "details": details or {},
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(CoreError)
    async def handle_app_error(request: Request, exc: CoreError) -> JSONResponse:
        request.state.public_error_code = exc.code
        response = _error_response(
            request,
            status_code=http_status(exc),
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )
        origin = getattr(request.state, "public_origin", None)
        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
        if "retry_after_seconds" in exc.details:
            response.headers["Retry-After"] = str(exc.details["retry_after_seconds"])
        return response

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _error_response(
            request,
            status_code=422,
            code="VALIDATION_ERROR",
            message="Request validation failed.",
            details={
                "errors": [
                    {"loc": error["loc"], "type": error["type"], "msg": "Invalid field value"}
                    for error in exc.errors()
                ]
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled request error", exc_info=exc)
        return _error_response(
            request,
            status_code=500,
            code="INTERNAL_ERROR",
            message="An unexpected error occurred.",
        )
