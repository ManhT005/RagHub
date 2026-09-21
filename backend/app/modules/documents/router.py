from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.modules.documents.schemas import DocumentAccepted
from app.modules.documents.service import DocumentService

router = APIRouter(prefix="/workspaces", tags=["documents"])


@router.post(
    "/{workspace_id}/documents",
    response_model=DocumentAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    workspace_id: UUID,
    organization_id: Annotated[UUID, Header(alias="X-Organization-ID")],
    file: Annotated[UploadFile, File()],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DocumentAccepted:
    service = DocumentService(session)
    return await service.upload_pdf(
        organization_id=organization_id,
        workspace_id=workspace_id,
        upload=file,
    )
