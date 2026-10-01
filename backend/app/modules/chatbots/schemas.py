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
    model: str | None
    retrieval_limit: int
    published: bool
    allowed_origins: list[str] = []
    embed_primary_color: str = "#1463ff"
    embed_title: str = "RagHub Assistant"
    embed_greeting: str = "Xin chao! Toi co the giup gi cho ban?"
    created_at: datetime
    updated_at: datetime | None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4_000)
    conversation_id: UUID | None = None
    external_user_id: str | None = Field(default=None, max_length=255)


class EmbedPublishInput(BaseModel):
    allowed_origins: list[str] = Field(min_length=1, max_length=20)
    primary_color: str = Field(default="#1463ff", pattern=r"^#[0-9A-Fa-f]{6}$")
    title: str = Field(default="RagHub Assistant", min_length=1, max_length=120)
    greeting: str = Field(default="Xin chao! Toi co the giup gi cho ban?", min_length=1, max_length=1000)


class EmbedCodeResponse(BaseModel):
    code: str
    key: str | None = None
