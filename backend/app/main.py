from fastapi import FastAPI

import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestIdMiddleware
from app.core.public_observability import PublicChatObservability
from app.core.redis import redis_lifespan
from app.modules.admin.router import router as admin_router
from app.modules.ai_providers.control_router import router as provider_control_router
from app.modules.ai_providers.router import router as ai_providers_router
from app.modules.ai_providers.workspace_ai_router import router as workspace_ai_router
from app.modules.auth.router import router as auth_router
from app.modules.chatbots.router import router as chatbots_router
from app.modules.documents.router import router as documents_router
from app.modules.health.router import router as health_router
from app.modules.organizations.router import router as organizations_router
from app.modules.search.router import router as search_router
from app.modules.workspace_access.router import router as workspace_access_router
from app.modules.workspaces.router import router as workspaces_router

configure_logging()
settings = get_settings()

app = FastAPI(
    lifespan=redis_lifespan,
    title=settings.app_name,
    version="0.1.0",
    docs_url=f"{settings.api_v1_prefix}/docs",
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    redoc_url=None,
)
app.add_middleware(PublicChatObservability)
app.add_middleware(RequestIdMiddleware)
register_exception_handlers(app)
app.include_router(health_router)
app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(admin_router, prefix=settings.api_v1_prefix)
app.include_router(ai_providers_router, prefix=settings.api_v1_prefix)
app.include_router(provider_control_router, prefix=settings.api_v1_prefix)
app.include_router(workspace_ai_router, prefix=settings.api_v1_prefix)
app.include_router(chatbots_router, prefix=settings.api_v1_prefix)
app.include_router(organizations_router, prefix=settings.api_v1_prefix)
app.include_router(workspaces_router, prefix=settings.api_v1_prefix)
app.include_router(workspace_access_router, prefix=settings.api_v1_prefix)
app.include_router(documents_router, prefix=settings.api_v1_prefix)
app.include_router(search_router, prefix=settings.api_v1_prefix)
