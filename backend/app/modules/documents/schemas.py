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
    embedded_chunks: int | None = None
    total_chunks: int | None = None
    queue_position: int | None = None
    waiting_reason: str | None = None
    work_state: str | None = None
    retry_at: datetime | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    chunk_count: int | None = None
    indexed_at: datetime | None = None
    embedding_model_id: UUID | None = None
    embedding_model_name: str | None = None
    embedding_dimension: int | None = None


class DocumentDetail(DocumentResponse):
    checksum: str | None = None
    chunk_strategy: str = "450 tokens / overlap 80"
