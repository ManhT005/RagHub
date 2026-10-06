from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    OrganizationContext,
    get_organization_context,
    require_workspace_permission,
)
from app.core.database import get_session
from app.core.exceptions import AppError
from app.modules.ai_providers.models import (
    EmbeddingIndexVersion,
    EmbeddingReindexJob,
    ProviderConfig,
)
from app.modules.ai_providers.schemas import RerankOptions, WorkspaceProviderBindingResponse
from app.modules.ai_providers.service import ProviderConfigService
from app.modules.documents.models import Document
from app.modules.workspaces.models import Workspace

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["workspace AI"])
Context = Annotated[OrganizationContext, Depends(get_organization_context)]
Session = Annotated[AsyncSession, Depends(get_session)]


class ModelSelection(BaseModel):
    model_id: UUID


class RerankSelection(RerankOptions):
    model_id: UUID | None = None


@router.get("/rerank-model")
async def get_rerank(workspace_id: UUID, context: Context, session: Session):
    await require_workspace_permission(context, workspace_id, "workspace.view", session)
    item = await workspace(session, context.organization_id, workspace_id)
    return {
        "model_id": item.rerank_provider_id,
        **RerankOptions.model_validate(item.rerank_config or {}).model_dump(),
    }


@router.put("/rerank-model")
async def change_rerank(
    workspace_id: UUID, payload: RerankSelection, context: Context, session: Session
):
    await require_workspace_permission(context, workspace_id, "workspace.edit", session)
    item = await workspace(session, context.organization_id, workspace_id)
    if payload.model_id:
        service = ProviderConfigService(session)
        available(await service.get(context.organization_id, payload.model_id), "RERANK")
    item.rerank_provider_id = payload.model_id
    item.rerank_config = payload.model_dump(exclude={"model_id"})
    await session.commit()
    return payload


class EmbeddingPreview(BaseModel):
    current_model: dict | None
    target_model: dict
    requires_reindex: bool
    documents_affected: int
    chunks_affected: int | None


def available(config: ProviderConfig, capability: str):
    connection = config.connection
    if (
        config.capability != capability
        or not config.enabled
        or config.availability_status != "AVAILABLE"
        or connection is None
        or not connection.enabled
        or connection.status != "CONNECTED"
    ):
        raise AppError(
            "MODEL_NOT_AVAILABLE", "A healthy registered model is required.", status_code=409
        )


async def workspace(session, organization_id, workspace_id):
    item = await session.scalar(
        select(Workspace)
        .where(
            Workspace.id == workspace_id,
            Workspace.organization_id == organization_id,
            Workspace.deleted_at.is_(None),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if item is None:
        raise AppError("WORKSPACE_NOT_FOUND", "Workspace not found.", status_code=404)
    return item


@router.post("/embedding-model/preview", response_model=EmbeddingPreview)
async def preview(workspace_id: UUID, payload: ModelSelection, context: Context, session: Session):
    await require_workspace_permission(context, workspace_id, "ai.change_embedding", session)
    item = await workspace(session, context.organization_id, workspace_id)
    target = await ProviderConfigService(session).get(context.organization_id, payload.model_id)
    available(target, "EMBEDDING")
    current = (
        await session.get(EmbeddingIndexVersion, item.active_embedding_index_version_id)
        if item.active_embedding_index_version_id
        else None
    )
    from app.modules.workspaces.summary import latest_versions

    latest = latest_versions()
    stats = (
        await session.execute(
            select(
                func.count(Document.id),
                func.count(latest.c.chunk_count),
                func.sum(latest.c.chunk_count),
            )
            .outerjoin(
                latest,
                (latest.c.document_id == Document.id) & (latest.c.rank == 1),
            )
            .where(
                Document.organization_id == context.organization_id,
                Document.workspace_id == workspace_id,
                Document.deleted_at.is_(None),
                Document.status == "READY",
            )
        )
    ).one()
    from app.modules.ai_providers.service import embedding_fingerprint

    return EmbeddingPreview(
        current_model={
            "id": str(current.provider_config_id),
            "model": current.model,
            "dimension": current.dimension,
            "provider_type": current.provider_type,
        }
        if current
        else None,
        target_model={
            "id": str(target.id),
            "model": target.model,
            "dimension": target.dimension,
            "provider_type": target.provider_type,
        },
        requires_reindex=not current
        or current.embedding_fingerprint != embedding_fingerprint(target),
        documents_affected=stats[0],
        chunks_affected=stats[2] if stats[0] == stats[1] else None,
    )


@router.put("/embedding-model", response_model=WorkspaceProviderBindingResponse)
async def change_embedding(
    workspace_id: UUID, payload: ModelSelection, context: Context, session: Session
):
    await require_workspace_permission(context, workspace_id, "ai.change_embedding", session)
    service = ProviderConfigService(session)
    available(await service.get(context.organization_id, payload.model_id), "EMBEDDING")
    current = await workspace(session, context.organization_id, workspace_id)
    if current.pending_embedding_index_version_id:
        pending = await session.scalar(
            select(EmbeddingReindexJob).where(
                EmbeddingReindexJob.target_index_version_id
                == current.pending_embedding_index_version_id,
            )
        )
        if pending and pending.status in {"QUEUED", "RUNNING", "VALIDATING", "SWITCHING"}:
            raise AppError("REINDEX_IN_PROGRESS", "Reindex is in progress.", status_code=409)
    item, job = await service.bind_workspace(
        context.organization_id,
        workspace_id,
        embedding_provider_id=payload.model_id,
        chat_provider_id=None,
    )
    return WorkspaceProviderBindingResponse(
        workspace_id=item.id,
        embedding_provider_id=item.embedding_provider_id,
        chat_provider_id=item.chat_provider_id,
        active_embedding_index_version_id=item.active_embedding_index_version_id,
        reindex_job_id=job.id if job else None,
    )


@router.put("/chat-model", response_model=WorkspaceProviderBindingResponse)
async def change_chat(
    workspace_id: UUID, payload: ModelSelection, context: Context, session: Session
):
    await require_workspace_permission(context, workspace_id, "workspace.edit", session)
    service = ProviderConfigService(session)
    available(await service.get(context.organization_id, payload.model_id), "CHAT")
    item, _ = await service.bind_workspace(
        context.organization_id,
        workspace_id,
        embedding_provider_id=None,
        chat_provider_id=payload.model_id,
    )
    return WorkspaceProviderBindingResponse(
        workspace_id=item.id,
        embedding_provider_id=item.embedding_provider_id,
        chat_provider_id=item.chat_provider_id,
        active_embedding_index_version_id=item.active_embedding_index_version_id,
    )
