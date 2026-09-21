from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DocumentAccepted(BaseModel):
    document_id: UUID
    document_version_id: UUID
    job_id: UUID
    status: str
    created_at: datetime
