from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    OrganizationContext,
    get_organization_context,
    require_role,
    require_workspace_permission,
)
from app.core.database import get_session
from app.core.exceptions import AppError
from app.modules.ai_providers.models import EmbeddingReindexJob, ProviderConfig
from app.modules.ai_providers.schemas import (
    EmbeddingReindexJobResponse,
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
        has_secret=bool(
            config.connection.encrypted_secret
            if getattr(config, "connection", None)
            else config.encrypted_secret
        ),
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


def reindex_job_response(job: EmbeddingReindexJob) -> EmbeddingReindexJobResponse:
    return EmbeddingReindexJobResponse(
        id=job.id,
        workspace_id=job.workspace_id,
        target_index_version_id=job.target_index_version_id,
        status=job.status,
        total_documents=job.total_documents,
        processed_documents=job.processed_documents,
        failed_documents=job.failed_documents,
        error_code=job.error_code,
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


def _manage(context: OrganizationContext) -> None:
    require_role(context, MembershipRole.ADMIN)


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
    deprecated=True,
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
    if payload.provider_type not in {"LOCAL_TOKEN_HASH", "LOCAL_SENTENCE_TRANSFORMER", "OLLAMA"}:
        raise AppError(
            "DEPRECATED_PROVIDER_API",
            "Create a connection and register its models.",
            status_code=410,
        )
    return provider_response(await ProviderConfigService(session).create(organization_id, payload))


@router.patch("/providers/{provider_id}", response_model=ProviderConfigResponse, deprecated=True)
async def update_provider(
    provider_id: UUID,
    payload: ProviderConfigPatch,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProviderConfigResponse:
    _manage(context)
    config = await ProviderConfigService(session).get(context.organization_id, provider_id)
    if config.provider_type not in {"LOCAL_TOKEN_HASH", "LOCAL_SENTENCE_TRANSFORMER", "OLLAMA"}:
        raise AppError(
            "DEPRECATED_PROVIDER_API", "Update the connection or registered model.", status_code=410
        )
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


@router.post("/embedding-reindex-jobs/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_embedding_reindex(
    job_id: UUID,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    from sqlalchemy import select

    job = await session.scalar(
        select(EmbeddingReindexJob).where(
            EmbeddingReindexJob.id == job_id,
            EmbeddingReindexJob.organization_id == context.organization_id,
        )
    )
    if job is None:
        raise AppError("REINDEX_JOB_NOT_FOUND", "Re-index job not found.", status_code=404)
    await require_workspace_permission(context, job.workspace_id, "ai.change_embedding", session)
    job = await ProviderConfigService(session).retry_reindex(context.organization_id, job_id)
    return {"job_id": job.id, "status": job.status}


@router.get(
    "/workspaces/{workspace_id}/embedding-reindex-jobs/{job_id}",
    response_model=EmbeddingReindexJobResponse,
)
async def get_embedding_reindex_job(
    workspace_id: UUID,
    job_id: UUID,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EmbeddingReindexJobResponse:
    await require_workspace_permission(context, workspace_id, "workspace.view", session)
    job = await ProviderConfigService(session).get_reindex_job(
        context.organization_id, workspace_id, job_id
    )
    return reindex_job_response(job)
