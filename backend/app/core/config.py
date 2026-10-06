from functools import lru_cache
from ipaddress import ip_network
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"
    app_name: str = "RagHub API"
    app_secret_key: str = "change-me-in-local-env"
    provider_master_key: str = "change-me-provider-key"
    access_token_ttl_minutes: int = Field(default=15, ge=1)
    refresh_token_ttl_days: int = Field(default=7, ge=1)
    password_reset_ttl_minutes: int = Field(default=15, ge=5, le=60)
    api_v1_prefix: str = "/api/v1"
    max_upload_size_mb: int = Field(default=25, ge=1, le=500)

    database_url: str = "postgresql+asyncpg://raghub:raghub-local-only@localhost:5432/raghub"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    elasticsearch_url: str = "http://localhost:9200"

    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "raghub"
    s3_secret_key: str = "raghub-local-only"
    s3_bucket: str = "raghub-documents"
    s3_secure: bool = False

    gemini_api_key: str = ""
    groq_api_key: str = ""
    cerebras_api_key: str = ""
    openrouter_api_key: str = ""
    openai_api_key: str = ""
    voyage_api_key: str = ""
    siliconflow_api_key: str = ""
    cloudflare_account_id: str = ""
    cloudflare_api_token: str = ""
    huggingface_token: str = ""
    nvidia_nim_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    gemini_model: str = "gemini-3.5-flash-lite"
    chat_provider_timeout_seconds: float = Field(default=45, ge=1, le=120)
    public_chat_requests_per_ip: int = Field(default=20, ge=1)
    public_chat_requests_per_chatbot: int = Field(default=120, ge=1)
    public_chat_concurrent_per_chatbot: int = Field(default=4, ge=1)
    public_chat_concurrent_global: int = Field(default=32, ge=1)
    public_chat_stream_timeout_seconds: float = Field(default=90, ge=1, le=600)
    public_chat_trusted_proxy_cidrs: str = ""
    ollama_base_url: str = "http://ollama:11434"

    rag_max_context_tokens: int = Field(default=6000, ge=1)
    rag_model_context_window: int | None = Field(default=None, ge=2048)
    rag_max_output_tokens: int = Field(default=1024, ge=1, le=32768)
    rag_prompt_safety_margin: int = Field(default=256, ge=0, le=8192)
    rag_embedding_cache_enabled: bool = False
    rag_embedding_batch_max_chunks: int = Field(default=24, ge=1, le=100)
    rag_embedding_batch_target_tokens: int = Field(default=10000, ge=100, le=100000)
    rag_ocr_enabled: bool = False
    rag_index_gc_enabled: bool = False

    rag_retrieval_candidates: int = Field(default=25, ge=10, le=100)
    rag_rrf_k: int = Field(default=60, ge=1, le=200)
    rag_max_chunks_per_document: int = Field(default=1, ge=1, le=25)
    rag_adaptive_clarification_enabled: bool = False
    rag_evidence_selection_enabled: bool = False
    rag_adaptive_rerank_enabled: bool = False
    rag_confidence_high_threshold: float = Field(default=0.85, gt=0, lt=1)
    rag_clarification_medium_threshold: float = Field(default=0.75, gt=0, lt=1)
    rag_neighbor_expansion_enabled: bool = False
    rag_relevance_gate_enabled: bool = False
    rag_relevance_config_version: str = "baseline-v1"
    rag_relevance_artifact_path: str = ""
    rag_reranker_snapshot_path: str = ""
    rag_reranker_expected_sha256: str = ""
    rag_reranker_timeout_seconds: float = Field(default=2, ge=0.1, le=120)
    rag_reranker_enabled: bool = False
    rag_rerank_top_n: int = Field(default=8, ge=1, le=25)
    rag_rerank_source_count: int = Field(default=25, ge=5, le=100)
    rag_hardware_profile: Literal["custom", "lite_cpu", "standard_cpu", "gpu"] = "custom"

    @model_validator(mode="before")
    @classmethod
    def hardware_profile_defaults(cls, values):
        from app.composition.hardware_profiles import apply_profile

        return apply_profile(values)

    provider_pool_max_active_jobs_per_workspace: int = Field(default=1, ge=1, le=10)
    provider_pool_max_pending_jobs_per_workspace: int = Field(default=5, ge=1, le=100)
    gemini_embedding_batch_max_chunks: int = Field(default=24, ge=1, le=100)
    gemini_embedding_batch_target_tokens: int = Field(default=10_000, ge=1_000, le=100_000)
    gemini_embedding_ingestion_tpm: int = Field(default=21_000, ge=1_000, le=30_000)
    gemini_embedding_ingestion_rpm: int = Field(default=80, ge=1, le=100)
    gemini_embedding_ingestion_rpd: int = Field(default=900, ge=1, le=1_000)
    trusted_local_provider_hosts: str = ""
    ai_rerank_enabled: bool = True
    local_ai_download_enabled: bool = True
    local_ai_model_dir: str = ".cache/huggingface/local-ai"

    frontend_url: str = "http://localhost:8080"
    public_base_url: str = ""
    public_base_url_allow_http: bool = False
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True

    @field_validator("public_base_url")
    @classmethod
    def validate_public_base_url(cls, value: str) -> str:
        if not value:
            return ""
        try:
            parsed = urlsplit(value)
            port = parsed.port
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or "?" in value
                or "#" in value
                or "\\" in value
                or "*" in value
                or any(ord(char) <= 32 for char in value)
                or (port is not None and port < 1)
            ):
                raise ValueError("invalid origin")
            host = parsed.hostname.encode("idna").decode("ascii").lower()
            if ":" in host:
                from ipaddress import IPv6Address

                IPv6Address(host)
                host = f"[{host}]"
            elif not all(char.isalnum() or char in ".-" for char in host):
                raise ValueError("invalid host")
            if port == {"http": 80, "https": 443}[parsed.scheme]:
                port = None
            return f"{parsed.scheme}://{host}" + (f":{port}" if port else "")
        except (ValueError, UnicodeError) as exc:
            raise ValueError(
                "PUBLIC_BASE_URL must be an HTTP(S) origin without paths or credentials"
            ) from exc

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if (
            self.app_env.lower() == "production"
            and self.public_base_url.startswith("http://")
            and not self.public_base_url_allow_http
        ):
            raise ValueError(
                "PUBLIC_BASE_URL requires HTTPS in production; private installs may explicitly "
                "set PUBLIC_BASE_URL_ALLOW_HTTP=true"
            )
        for cidr in self.public_chat_trusted_proxy_cidrs.split(","):
            if cidr.strip():
                ip_network(cidr.strip())
        insecure_provider_keys = {
            "",
            "change-me-provider-key",
            "local-provider-key-change-before-production",
            "replace-with-a-dedicated-provider-encryption-key",
        }
        if self.app_env.lower() not in {"development", "dev", "local", "test"}:
            if len(self.app_secret_key) < 32 or self.app_secret_key == "change-me-in-local-env":
                raise ValueError("APP_SECRET_KEY must be a dedicated key of at least 32 characters")
            if self.provider_master_key in insecure_provider_keys:
                raise ValueError("PROVIDER_MASTER_KEY must be set to a dedicated production key")
            if self.app_env.lower() != "selfhost" and not all(
                (
                    self.smtp_host,
                    self.smtp_username,
                    self.smtp_password,
                    self.smtp_from_email,
                )
            ):
                raise ValueError("Gmail SMTP settings are required outside development")
            email_settings = (
                self.smtp_host,
                self.smtp_username,
                self.smtp_password,
                self.smtp_from_email,
            )
            if any(email_settings) and not all(email_settings):
                raise ValueError("SMTP configuration must be complete when enabled")
        return self

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() in {"development", "dev", "local", "test"}

    @property
    def cookie_secure(self) -> bool:
        return not self.is_development

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def sqlalchemy_sync_url(self) -> str:
        return self.database_url.replace("+asyncpg", "+psycopg")


@lru_cache
def get_settings() -> Settings:
    return Settings()
