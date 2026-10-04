from sqlalchemy import case, func, select

from app.modules.ai_providers.models import (
    EmbeddingIndexVersion,
    EmbeddingReindexJob,
    ProviderConfig,
)
from app.modules.documents.models import Document, DocumentIndexMetadata, DocumentVersion
from app.modules.memberships.models import Membership, WorkspaceMembership
from app.modules.users.models import User
from app.modules.workspaces.models import Workspace


def latest_versions():
    return select(
        DocumentVersion,
        func.row_number()
        .over(
            partition_by=DocumentVersion.document_id,
            order_by=(DocumentVersion.created_at.desc(), DocumentVersion.id.desc()),
        )
        .label("rank"),
    ).subquery()


def summary_statement(organization_id):
    latest = latest_versions()
    documents = (
        select(
            Document.workspace_id,
            func.count().label("document_count"),
            case(
                (
                    func.count(DocumentIndexMetadata.chunk_count) == func.count(Document.id),
                    func.sum(DocumentIndexMetadata.chunk_count),
                ),
                else_=None,
            ).label("chunk_count"),
            func.max(DocumentIndexMetadata.indexed_at).label("last_indexed_at"),
        )
        .join(Workspace, Workspace.id == Document.workspace_id)
        .outerjoin(
            latest,
            (latest.c.document_id == Document.id) & (latest.c.rank == 1),
        )
        .outerjoin(
            DocumentIndexMetadata,
            (DocumentIndexMetadata.document_version_id == latest.c.id)
            & (
                DocumentIndexMetadata.embedding_index_version_id
                == Workspace.active_embedding_index_version_id
            ),
        )
        .where(Document.organization_id == organization_id, Document.deleted_at.is_(None))
        .group_by(Document.workspace_id)
        .subquery()
    )
    members = (
        select(WorkspaceMembership.workspace_id, func.count().label("member_count"))
        .join(
            Membership,
            Membership.user_id == WorkspaceMembership.user_id,
        )
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.organization_id == organization_id,
            Membership.status == "ACTIVE",
            User.status == "ACTIVE",
        )
        .group_by(WorkspaceMembership.workspace_id)
        .subquery()
    )
    return (
        select(
            Workspace,
            documents.c.document_count,
            documents.c.chunk_count,
            documents.c.last_indexed_at,
            members.c.member_count,
            EmbeddingIndexVersion,
            ProviderConfig,
            EmbeddingReindexJob.id.label("reindex_job_id"),
            EmbeddingReindexJob.status.label("reindex_status"),
        )
        .outerjoin(documents, documents.c.workspace_id == Workspace.id)
        .outerjoin(
            members,
            members.c.workspace_id == Workspace.id,
        )
        .outerjoin(
            EmbeddingIndexVersion,
            EmbeddingIndexVersion.id == Workspace.active_embedding_index_version_id,
        )
        .outerjoin(
            ProviderConfig,
            ProviderConfig.id == EmbeddingIndexVersion.provider_config_id,
        )
        .outerjoin(
            EmbeddingReindexJob,
            EmbeddingReindexJob.target_index_version_id
            == Workspace.pending_embedding_index_version_id,
        )
        .where(
            Workspace.organization_id == organization_id,
            Workspace.deleted_at.is_(None),
        )
    )


def summary_data(row):
    workspace, docs, chunks, indexed, members, version, config, job_id, job_status = row
    model = None
    if version:
        model = {
            "id": str(version.provider_config_id),
            "model": version.model,
            "provider_name": config.connection.name
            if config and config.connection
            else version.provider_type,
            "provider_type": version.provider_type,
            "dimension": version.dimension,
            "status": config.availability_status if config else "UNTESTED",
        }
    return {
        "id": workspace.id,
        "name": workspace.name,
        "slug": workspace.slug,
        "organization_id": workspace.organization_id,
        "created_at": workspace.created_at,
        "updated_at": workspace.updated_at,
        "member_count": members or 0,
        "document_count": docs or 0,
        "chunk_count": chunks if chunks is not None else None,
        "last_indexed_at": indexed,
        "embedding_model": model,
        "chat_provider_id": workspace.chat_provider_id,
        "status": "REINDEXING"
        if job_status in {"QUEUED", "RUNNING", "VALIDATING", "SWITCHING"}
        else "WARNING"
        if job_status in {"FAILED", "QUEUE_FAILED"}
        else "ACTIVE"
        if version
        else "AI_NOT_CONFIGURED",
        "reindex_job_id": job_id,
        "reindex_status": job_status,
    }
