from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ChatbotInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    system_prompt: str = Field(default="", max_length=12_000)
    model: str | None = Field(default=None, min_length=1, max_length=200)
    retrieval_limit: int = Field(default=5, ge=1, le=10)
    published: bool = False


class ChatbotPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    system_prompt: str | None = Field(default=None, max_length=12_000)
    model: str | None = Field(default=None, min_length=1, max_length=200)
    retrieval_limit: int | None = Field(default=None, ge=1, le=10)
    published: bool | None = None


class ChatbotResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    system_prompt: str
    model: str
    retrieval_limit: int
    published: bool
    created_at: datetime
    updated_at: datetime | None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4_000)
    conversation_id: UUID | None = None
    external_user_id: str | None = Field(default=None, max_length=255)
