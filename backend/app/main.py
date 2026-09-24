from fastapi import FastAPI

import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestIdMiddleware
from app.modules.auth.router import router as auth_router
from app.modules.chatbots.router import router as chatbots_router
from app.modules.documents.router import router as documents_router
from app.modules.health.router import router as health_router
from app.modules.organizations.router import router as organizations_router
from app.modules.search.router import router as search_router
from app.modules.workspaces.router import router as workspaces_router

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
app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(chatbots_router, prefix=settings.api_v1_prefix)
app.include_router(organizations_router, prefix=settings.api_v1_prefix)
app.include_router(workspaces_router, prefix=settings.api_v1_prefix)
app.include_router(documents_router, prefix=settings.api_v1_prefix)
app.include_router(search_router, prefix=settings.api_v1_prefix)
