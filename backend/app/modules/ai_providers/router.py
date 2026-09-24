from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import OrganizationContext, get_organization_context, require_role
from app.core.database import get_session
from app.core.exceptions import AppError
from app.modules.ai_providers.models import ProviderConfig
from app.modules.ai_providers.schemas import (
    ProviderConfigInput,
    ProviderConfigPatch,
    ProviderConfigResponse,
    ProviderTestResponse,
    WorkspaceProviderBindingInput,
    WorkspaceProviderBindingResponse,
)
from app.modules.ai_providers.service import ProviderConfigService
from app.modules.memberships.models import MembershipRole

router = APIRouter(tags=["AI providers"])


def provider_response(config: ProviderConfig) -> ProviderConfigResponse:
    return ProviderConfigResponse(
        id=config.id,
        organization_id=config.organization_id,
        name=config.name,
        provider_type=config.provider_type,
        capability=config.capability,
        base_url=config.base_url,
        model=config.model,
        dimension=config.dimension,
        config_json=config.config_json or {},
        enabled=config.enabled,
        has_secret=bool(config.encrypted_secret),
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


def _manage(context: OrganizationContext) -> None:
    require_role(context, MembershipRole.OWNER, MembershipRole.ADMIN)


@router.get(
    "/organizations/{organization_id}/providers", response_model=list[ProviderConfigResponse]
)
async def list_providers(
    organization_id: UUID,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ProviderConfigResponse]:
    if context.organization_id != organization_id:
        raise AppError(
            "ORGANIZATION_SCOPE_MISMATCH", "Organization scope mismatch.", status_code=400
        )
    _manage(context)
    configs = await ProviderConfigService(session).list(organization_id)
    return [provider_response(item) for item in configs]


@router.post(
    "/organizations/{organization_id}/providers",
    response_model=ProviderConfigResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_provider(
    organization_id: UUID,
    payload: ProviderConfigInput,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProviderConfigResponse:
    if context.organization_id != organization_id:
        raise AppError(
            "ORGANIZATION_SCOPE_MISMATCH", "Organization scope mismatch.", status_code=400
        )
    _manage(context)
    return provider_response(await ProviderConfigService(session).create(organization_id, payload))


@router.patch("/providers/{provider_id}", response_model=ProviderConfigResponse)
async def update_provider(
    provider_id: UUID,
    payload: ProviderConfigPatch,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProviderConfigResponse:
    _manage(context)
    return provider_response(
        await ProviderConfigService(session).update(context.organization_id, provider_id, payload)
    )


@router.post("/providers/{provider_id}/test", response_model=ProviderTestResponse)
async def test_provider(
    provider_id: UUID,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProviderTestResponse:
    _manage(context)
    result = await ProviderConfigService(session).test(context.organization_id, provider_id)
    return ProviderTestResponse.model_validate(result)


@router.delete("/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider_id: UUID,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    _manage(context)
    await ProviderConfigService(session).delete(context.organization_id, provider_id)


@router.patch(
    "/workspaces/{workspace_id}/providers", response_model=WorkspaceProviderBindingResponse
)
async def bind_workspace_providers(
    workspace_id: UUID,
    payload: WorkspaceProviderBindingInput,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WorkspaceProviderBindingResponse:
    _manage(context)
    workspace, job = await ProviderConfigService(session).bind_workspace(
        context.organization_id,
        workspace_id,
        embedding_provider_id=payload.embedding_provider_id,
        chat_provider_id=payload.chat_provider_id,
    )
    return WorkspaceProviderBindingResponse(
        workspace_id=workspace.id,
        embedding_provider_id=workspace.embedding_provider_id,
        chat_provider_id=workspace.chat_provider_id,
        active_embedding_index_version_id=workspace.active_embedding_index_version_id,
        reindex_job_id=job.id if job else None,
    )
