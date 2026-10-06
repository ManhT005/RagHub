from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from raghub_core.domain.errors import CoreError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    OrganizationContext,
    get_organization_context,
    require_role,
    require_workspace_permission,
)
from app.core.database import get_session
from app.core.exceptions import AppError
from app.modules.ai_providers.catalog import CATALOG, CatalogItem
from app.modules.ai_providers.control_schemas import (
    ConnectionInput,
    ConnectionPatch,
    ConnectionResponse,
    ConnectionTestResponse,
    DiscoveredModel,
    ModelInput,
    ModelPatch,
    ModelResponse,
    OllamaPullInput,
    OllamaPullResponse,
)
from app.modules.ai_providers.control_service import (
    ProviderControlService,
    connection_response,
    health_error,
    model_response,
)
from app.modules.ai_providers.models import OllamaModelPull
from app.modules.ai_providers.ollama_manager import OllamaModelManager, ollama_connection
from app.modules.ai_providers.ollama_recommendations import RECOMMENDATIONS
from app.modules.ai_providers.service import ProviderConfigService
from app.modules.memberships.models import MembershipRole

router = APIRouter(tags=["provider control plane"])
Context = Annotated[OrganizationContext, Depends(get_organization_context)]
Session = Annotated[AsyncSession, Depends(get_session)]


def admin(context, organization_id=None):
    require_role(context, MembershipRole.ADMIN)
    if organization_id is not None and organization_id != context.organization_id:
        raise AppError(
            "ORGANIZATION_SCOPE_MISMATCH", "Organization scope mismatch.", status_code=400
        )


@router.get("/ai/provider-catalog", response_model=list[CatalogItem])
async def catalog(context: Context):
    admin(context)
    return CATALOG


@router.get(
    "/organizations/{organization_id}/provider-connections", response_model=list[ConnectionResponse]
)
async def connections(organization_id: UUID, context: Context, session: Session):
    admin(context, organization_id)
    return await ProviderControlService(session).list(organization_id)


@router.post(
    "/organizations/{organization_id}/provider-connections",
    response_model=ConnectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create(
    organization_id: UUID, payload: ConnectionInput, context: Context, session: Session
):
    admin(context, organization_id)
    return connection_response(
        await ProviderControlService(session).create(organization_id, payload)
    )


@router.get("/provider-connections/{connection_id}", response_model=ConnectionResponse)
async def get(connection_id: UUID, context: Context, session: Session):
    admin(context)
    return connection_response(
        await ProviderControlService(session).get(context.organization_id, connection_id)
    )


@router.patch("/provider-connections/{connection_id}", response_model=ConnectionResponse)
async def update(connection_id: UUID, payload: ConnectionPatch, context: Context, session: Session):
    admin(context)
    return connection_response(
        await ProviderControlService(session).update(
            context.organization_id, connection_id, payload
        )
    )


@router.delete("/provider-connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(connection_id: UUID, context: Context, session: Session):
    admin(context)
    await ProviderControlService(session).delete(context.organization_id, connection_id)


@router.post("/provider-connections/{connection_id}/test", response_model=ConnectionTestResponse)
async def test(connection_id: UUID, context: Context, session: Session):
    admin(context)
    return await ProviderControlService(session).test(context.organization_id, connection_id)


@router.post(
    "/provider-connections/{connection_id}/models/discover", response_model=list[DiscoveredModel]
)
async def discover(connection_id: UUID, context: Context, session: Session):
    admin(context)
    return await ProviderControlService(session).discover(context.organization_id, connection_id)


@router.get("/provider-connections/{connection_id}/ollama/recommendations")
async def ollama_recommendations(connection_id: UUID, context: Context, session: Session):
    admin(context)
    ollama_connection(
        await ProviderControlService(session).get(context.organization_id, connection_id)
    )
    return RECOMMENDATIONS


@router.post(
    "/provider-connections/{connection_id}/ollama/models/pull",
    response_model=OllamaPullResponse,
    status_code=202,
)
async def pull_ollama_model(
    connection_id: UUID, payload: OllamaPullInput, context: Context, session: Session
):
    admin(context)
    return await OllamaModelManager(session).start(context.organization_id, connection_id, payload)


@router.get(
    "/provider-connections/{connection_id}/ollama/model-pulls/{job_id}",
    response_model=OllamaPullResponse,
)
async def ollama_pull_status(connection_id: UUID, job_id: UUID, context: Context, session: Session):
    admin(context)
    return await OllamaModelManager(session).get(context.organization_id, connection_id, job_id)


@router.get(
    "/provider-connections/{connection_id}/ollama/model-pulls",
    response_model=list[OllamaPullResponse],
)
async def ollama_pulls(connection_id: UUID, context: Context, session: Session):
    admin(context)
    ollama_connection(
        await ProviderControlService(session).get(context.organization_id, connection_id)
    )
    return list(
        await session.scalars(
            select(OllamaModelPull)
            .where(
                OllamaModelPull.connection_id == connection_id,
                OllamaModelPull.organization_id == context.organization_id,
            )
            .order_by(OllamaModelPull.created_at.desc())
            .limit(10)
        )
    )


@router.post(
    "/provider-connections/{connection_id}/models", response_model=ModelResponse, status_code=201
)
async def register(connection_id: UUID, payload: ModelInput, context: Context, session: Session):
    admin(context)
    return model_response(
        await ProviderControlService(session).register(
            context.organization_id, connection_id, payload
        )
    )


@router.get("/organizations/{organization_id}/models", response_model=list[ModelResponse])
async def models(
    organization_id: UUID,
    context: Context,
    session: Session,
    capability: str | None = None,
    availability: str | None = None,
    provider_type: str | None = None,
):
    admin(context, organization_id)
    return await ProviderControlService(session).models(
        organization_id,
        capability=capability,
        availability=availability,
        provider_type=provider_type,
    )


@router.get("/models/{model_id}", response_model=ModelResponse)
async def model(model_id: UUID, context: Context, session: Session):
    admin(context)
    return model_response(
        await ProviderConfigService(session).get(context.organization_id, model_id)
    )


@router.patch("/models/{model_id}", response_model=ModelResponse)
async def update_model(model_id: UUID, payload: ModelPatch, context: Context, session: Session):
    admin(context)
    service = ProviderConfigService(session)
    config = await service.get(context.organization_id, model_id)
    if payload.enabled is False and await service._is_bound(context.organization_id, model_id):
        raise AppError("PROVIDER_IN_USE", "Model is used by a workspace.", status_code=409)
    if payload.display_name is not None:
        config.display_name = payload.display_name.strip()
    if payload.enabled is not None:
        config.enabled = payload.enabled
        config.availability_status = "UNTESTED" if payload.enabled else "DISABLED"
    await session.commit()
    return model_response(config)


@router.post("/models/{model_id}/test", response_model=ModelResponse)
async def test_model(model_id: UUID, context: Context, session: Session):
    admin(context)
    service = ProviderConfigService(session)
    config = await service.get(context.organization_id, model_id)
    try:
        await service.test(context.organization_id, model_id)
    except CoreError as exc:
        from datetime import UTC, datetime

        config.availability_status = "UNAVAILABLE"
        config.last_health_check_at = datetime.now(UTC)
        if config.connection is not None:
            config.connection.status = "DEGRADED"
            config.connection.last_error_code = health_error(exc)
        await session.commit()
        raise AppError(health_error(exc), "Model health check failed.", status_code=422) from exc
    return model_response(config)


@router.delete("/models/{model_id}", status_code=204)
async def delete_model(model_id: UUID, context: Context, session: Session):
    admin(context)
    await ProviderConfigService(session).delete(context.organization_id, model_id)


@router.get("/workspaces/{workspace_id}/models", response_model=list[ModelResponse])
async def workspace_models(
    workspace_id: UUID, context: Context, session: Session, capability: str = "EMBEDDING"
):
    await require_workspace_permission(context, workspace_id, "ai.view", session)
    models = await ProviderControlService(session).models(
        context.organization_id, capability=capability, availability="AVAILABLE"
    )
    return [
        model
        for model in models
        if model.enabled and model.connection_enabled and model.connection_status == "CONNECTED"
    ]
