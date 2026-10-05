from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from raghub_core.domain.providers.enums import ProviderCapability

from app.modules.ai_providers.catalog import supported_catalog_by_id
from app.modules.ai_providers.schemas import (
    _validate_base_url,
    _validate_provider_options,
    _validate_safe_config,
    validate_public_provider_url,
)


class ConnectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    provider_type: str
    catalog_id: str
    base_url: str | None = Field(default=None, max_length=1024)
    secret: str | None = Field(default=None, min_length=1, max_length=4096)
    enabled: bool = True
    config_json: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_connection(self):
        item = supported_catalog_by_id(self.catalog_id)
        if item.provider_type != self.provider_type:
            raise ValueError("Catalog identity must match the runtime provider type")
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("Connection name is required")
        self.base_url = _validate_base_url(self.base_url or item.default_base_url)
        if item.category != "Local":
            self.base_url = validate_public_provider_url(self.base_url)
        if self.provider_type == "OPENAI_COMPATIBLE" and not self.base_url:
            raise ValueError("Custom provider requires base URL")
        if item.auth_type == "NONE" and self.secret:
            raise ValueError("Local providers do not accept credentials")
        self.config_json = _validate_provider_options(_validate_safe_config(self.config_json))
        return self


class ConnectionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    catalog_id: str | None = None
    base_url: str | None = Field(default=None, max_length=1024)
    secret: str | None = Field(default=None, min_length=1, max_length=4096)
    clear_secret: bool = False
    enabled: bool | None = None
    config_json: dict[str, Any] | None = None

    @field_validator("catalog_id")
    @classmethod
    def validate_catalog_id(cls, value):
        if value is None:
            raise ValueError("Provider catalog identity cannot be cleared")
        supported_catalog_by_id(value)
        return value


class ConnectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    name: str
    provider_type: str
    catalog_id: str | None
    base_url: str | None
    enabled: bool
    has_secret: bool
    status: str
    last_tested_at: datetime | None
    last_latency_ms: int | None
    last_error_code: str | None
    created_at: datetime
    updated_at: datetime | None
    model_count: int = 0


class DiscoveredModel(BaseModel):
    model: str = Field(min_length=1, max_length=255)
    display_name: str | None = Field(default=None, max_length=200)
    capabilities: list[ProviderCapability] = Field(default_factory=list)
    dimension: int | None = None
    size_bytes: int | None = None


class OllamaPullInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str = Field(
        min_length=1,
        max_length=255,
        pattern=r"^(?:[a-zA-Z0-9_-]+/)?[a-zA-Z0-9][a-zA-Z0-9._-]*(?::[a-zA-Z0-9][a-zA-Z0-9._-]*)?$",
    )
    register_after_pull: bool = True


class OllamaPullResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    connection_id: UUID
    model: str
    status: str
    register_after_pull: bool
    completed_bytes: int
    total_bytes: int
    error_code: str | None
    registered_model_id: UUID | None
    created_at: datetime
    updated_at: datetime


class ModelInput(BaseModel):
    model: str = Field(min_length=1, max_length=255)
    display_name: str | None = Field(default=None, max_length=200)
    capability: ProviderCapability
    dimension: int | None = Field(default=None, gt=0, le=65536)


class ModelPatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    enabled: bool | None = None


class ModelResponse(BaseModel):
    id: UUID
    connection_id: UUID | None
    model: str
    display_name: str | None
    provider_name: str
    provider_type: str
    provider_catalog_id: str | None = None
    capability: str
    dimension: int | None
    availability_status: str
    connection_status: str
    connection_enabled: bool
    enabled: bool
    used_by_workspaces: int = 0
    last_health_check_at: datetime | None = None


class ConnectionTestResponse(BaseModel):
    status: str
    latency_ms: int
    capabilities: list[str]
    discovery_supported: bool
    error_code: str | None = None
