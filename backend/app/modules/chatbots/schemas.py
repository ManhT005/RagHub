from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.delivery.security.origins import normalize_origin

ClarificationMode = Literal["off", "conservative", "proactive"]


class ChatbotInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    system_prompt: str = Field(default="", max_length=12_000)
    model: str | None = Field(default=None, min_length=1, max_length=200)
    retrieval_limit: int = Field(default=5, ge=1, le=10)
    published: bool = False
    clarification_mode: ClarificationMode = "conservative"
    max_clarifying_turns: int = Field(default=1, ge=0, le=5)
    domain_profile: str = Field(default="admissions", min_length=1, max_length=64)


class ChatbotPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    system_prompt: str | None = Field(default=None, max_length=12_000)
    model: str | None = Field(default=None, min_length=1, max_length=200)
    retrieval_limit: int | None = Field(default=None, ge=1, le=10)
    published: bool | None = None
    clarification_mode: ClarificationMode | None = None
    max_clarifying_turns: int | None = Field(default=None, ge=0, le=5)
    domain_profile: str | None = Field(default=None, min_length=1, max_length=64)


class ChatbotResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    system_prompt: str
    model: str | None
    retrieval_limit: int
    published: bool
    clarification_mode: ClarificationMode = "conservative"
    max_clarifying_turns: int = 1
    domain_profile: str = "admissions"
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
    greeting: str = Field(
        default="Xin chao! Toi co the giup gi cho ban?", min_length=1, max_length=1000
    )

    @field_validator("allowed_origins")
    @classmethod
    def validate_origins(cls, values: list[str]) -> list[str]:
        normalized = [normalize_origin(value) for value in values]
        if any(value is None for value in normalized):
            raise ValueError(
                "Use explicit HTTP(S) origins without paths, credentials or wildcards."
            )
        return list(dict.fromkeys(normalized))


class EmbedCodeResponse(BaseModel):
    code: str | None = None
    key: str | None = None
    script_src: str
    public_base_url: str
    has_embed_key: bool = False
