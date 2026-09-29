from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AllowedOriginsInput(StrictModel):
    origins: list[str] = Field(max_length=100)


class AllowedOriginsResponse(BaseModel):
    origins: list[str]


class ApiKeyCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    expires_at: datetime | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Name must not be blank.")
        return value.strip()


class ApiKeyResponse(BaseModel):
    id: UUID
    name: str
    prefix: str
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    last_used_at: datetime | None


class ApiKeyCreatedResponse(ApiKeyResponse):
    api_key: str


class PublicConfigResponse(BaseModel):
    public_key: str
    name: str
    capabilities: dict[str, bool]
    limits: dict[str, int]


class PublicConversationInput(StrictModel):
    pass


class PublicConversationResponse(BaseModel):
    conversation_id: UUID
    conversation_token: str


class PublicChatRequest(StrictModel):
    message: str = Field(min_length=1, max_length=4_000)
    conversation_id: UUID
    conversation_token: str = Field(min_length=32, max_length=128)
