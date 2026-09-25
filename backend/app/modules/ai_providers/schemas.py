import ipaddress
import socket
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.ai_providers.enums import ProviderCapability, ProviderType

_SENSITIVE_CONFIG_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "credentials",
    "encrypted_secret",
    "password",
    "secret",
    "token",
}


def _validate_safe_config(config: dict[str, Any]) -> dict[str, Any]:
    def inspect(value: object) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if key.lower().replace("-", "_") in _SENSITIVE_CONFIG_KEYS:
                    raise ValueError("Secrets must be supplied through the secret field")
                inspect(nested)
        elif isinstance(value, list):
            for nested in value:
                inspect(nested)

    inspect(config)
    return config


class ProviderOptions(BaseModel):
    model_config = ConfigDict(extra="allow")

    connect_timeout: float | None = Field(default=None, strict=True, gt=0, le=300)
    read_timeout: float | None = Field(default=None, strict=True, gt=0, le=600)
    max_attempts: int | None = Field(default=None, strict=True, ge=1, le=5)
    backoff_seconds: float | None = Field(default=None, strict=True, ge=0, le=60)
    batch_size: int | None = Field(default=None, strict=True, ge=1, le=1024)
    max_concurrency: int | None = Field(default=None, strict=True, ge=1, le=64)
    options: dict[str, Any] | None = None


def _validate_provider_options(config: dict[str, Any]) -> dict[str, Any]:
    return ProviderOptions.model_validate(config).model_dump(exclude_none=True)


def _validate_base_url(url: str | None) -> str | None:
    if url is None:
        return None
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("base_url must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("base_url cannot contain credentials, query parameters, or fragments")
    return url


def validate_public_provider_url(url: str | None) -> str | None:
    url = _validate_base_url(url)
    if url is None:
        return None
    hostname = urlsplit(url).hostname
    if not hostname:
        raise ValueError("base_url must contain a hostname")
    addresses: set[str] = set()
    try:
        addresses.add(str(ipaddress.ip_address(hostname)))
    except ValueError:
        if hostname.lower() == "localhost" or hostname.lower().endswith(".localhost"):
            raise ValueError("base_url cannot target a local or private network") from None
        try:
            addresses.update(item[4][0] for item in socket.getaddrinfo(hostname, None))
        except socket.gaierror:
            # Connectivity testing will report an invalid/unresolvable custom hostname.
            return url
    if any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("base_url cannot target a local or private network")
    return url


class ProviderConfigInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    provider_type: ProviderType
    capability: ProviderCapability
    base_url: str | None = Field(default=None, max_length=1024)
    model: str = Field(min_length=1, max_length=255)
    dimension: int | None = Field(default=None, gt=0, le=65536)
    secret: str | None = Field(default=None, min_length=1, max_length=4096)
    config_json: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_capability(self) -> "ProviderConfigInput":
        self.base_url = _validate_base_url(self.base_url)
        self.config_json = _validate_provider_options(_validate_safe_config(self.config_json))
        supported = {
            ProviderType.OPENAI_COMPATIBLE: {
                ProviderCapability.EMBEDDING,
                ProviderCapability.CHAT,
            },
            ProviderType.GOOGLE_GEMINI: {
                ProviderCapability.EMBEDDING,
                ProviderCapability.CHAT,
            },
            ProviderType.LOCAL_SENTENCE_TRANSFORMER: {ProviderCapability.EMBEDDING},
            ProviderType.OLLAMA: {ProviderCapability.CHAT},
        }
        if self.capability not in supported[self.provider_type]:
            raise ValueError("The provider type does not support this capability")
        if self.provider_type in {
            ProviderType.OPENAI_COMPATIBLE,
            ProviderType.GOOGLE_GEMINI,
        }:
            self.base_url = validate_public_provider_url(self.base_url)
        if self.capability == ProviderCapability.EMBEDDING and self.dimension is None:
            raise ValueError("Embedding providers require dimension")
        if (
            self.provider_type
            in {
                ProviderType.LOCAL_SENTENCE_TRANSFORMER,
                ProviderType.OLLAMA,
            }
            and self.secret
        ):
            raise ValueError("Local providers do not accept a secret")
        return self


class ProviderConfigPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    base_url: str | None = Field(default=None, max_length=1024)
    model: str | None = Field(default=None, min_length=1, max_length=255)
    dimension: int | None = Field(default=None, gt=0, le=65536)
    secret: str | None = Field(default=None, min_length=1, max_length=4096)
    clear_secret: bool = False
    config_json: dict[str, Any] | None = None
    enabled: bool | None = None

    @model_validator(mode="after")
    def validate_safe_values(self) -> "ProviderConfigPatch":
        self.base_url = _validate_base_url(self.base_url)
        if self.config_json is not None:
            self.config_json = _validate_provider_options(_validate_safe_config(self.config_json))
        return self


class ProviderConfigResponse(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    provider_type: ProviderType
    capability: ProviderCapability
    base_url: str | None
    model: str
    dimension: int | None
    config_json: dict[str, Any]
    enabled: bool
    has_secret: bool
    created_at: datetime
    updated_at: datetime | None


class ProviderTestResponse(BaseModel):
    status: str
    capability: ProviderCapability
    provider: ProviderType
    model: str
    latency_ms: int
    dimension: int | None = None


class WorkspaceProviderBindingInput(BaseModel):
    embedding_provider_id: UUID | None = None
    chat_provider_id: UUID | None = None


class WorkspaceProviderBindingResponse(BaseModel):
    workspace_id: UUID
    embedding_provider_id: UUID | None
    chat_provider_id: UUID | None
    active_embedding_index_version_id: UUID | None
    reindex_job_id: UUID | None = None
