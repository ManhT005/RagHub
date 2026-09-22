from uuid import UUID

from pydantic import BaseModel, Field


class SearchHit(BaseModel):
    document_id: UUID
    document_version_id: UUID
    chunk_id: UUID
    content: str
    source_name: str
    page_number: int | None
    heading: str | None = None
    score: float


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit] = Field(default_factory=list)
