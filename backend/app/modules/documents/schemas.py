from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DocumentAccepted(BaseModel):
    document_id: UUID
    document_version_id: UUID
    job_id: UUID
    status: str
    created_at: datetime


class DocumentResponse(BaseModel):
    id: UUID
    name: str
    status: str
    created_at: datetime
    updated_at: datetime | None = None
    document_version_id: UUID | None = None
    job_id: UUID | None = None
    stage: str | None = None
    progress: int | None = None
    attempts: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
