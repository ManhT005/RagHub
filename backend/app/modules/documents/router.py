from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import OrganizationContext, get_organization_context, require_role
from app.core.database import get_session
from app.modules.documents.schemas import DocumentAccepted, DocumentResponse
from app.modules.documents.service import DocumentService
from app.modules.memberships.models import MembershipRole

router = APIRouter(prefix="/workspaces", tags=["documents"])


@router.post(
    "/{workspace_id}/documents",
    response_model=DocumentAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    workspace_id: UUID,
    file: Annotated[UploadFile, File()],
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DocumentAccepted:
    require_role(context, MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.EDITOR)
    service = DocumentService(session)
    return await service.upload_document(
        organization_id=context.organization_id,
        workspace_id=workspace_id,
        upload=file,
    )


@router.post(
    "/{workspace_id}/document-versions/{version_id}/retry",
    response_model=DocumentAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_document_version(
    workspace_id: UUID,
    version_id: UUID,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DocumentAccepted:
    require_role(context, MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.EDITOR)
    return await DocumentService(session).retry(context.organization_id, workspace_id, version_id)


@router.get("/{workspace_id}/documents", response_model=list[DocumentResponse])
async def list_documents(
    workspace_id: UUID,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[DocumentResponse]:
    return await DocumentService(session).list_documents(context.organization_id, workspace_id)


@router.delete("/{workspace_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    workspace_id: UUID,
    document_id: UUID,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> None:
    require_role(context, MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.EDITOR)
    await DocumentService(session).delete_document(
        context.organization_id, workspace_id, document_id
    )
