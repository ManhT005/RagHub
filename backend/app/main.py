from fastapi import FastAPI

import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestIdMiddleware
from app.modules.health.router import router as health_router

configure_logging()
settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url=f"{settings.api_v1_prefix}/docs",
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    redoc_url=None,
)
app.add_middleware(RequestIdMiddleware)
register_exception_handlers(app)
app.include_router(health_router)
