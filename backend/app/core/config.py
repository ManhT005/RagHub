from functools import lru_cache

from pydantic import Field, model_validator
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
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7
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
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    gemini_model: str = "gemini-3.5-flash-lite"
    chat_provider_timeout_seconds: float = Field(default=45, ge=1, le=120)
    public_chat_requests_per_ip: int = Field(default=20, ge=1)
    public_chat_requests_per_chatbot: int = Field(default=120, ge=1)
    ollama_base_url: str = "http://ollama:11434"

    frontend_url: str = "http://localhost:8080"
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        insecure_provider_keys = {
            "",
            "change-me-provider-key",
            "local-provider-key-change-before-production",
            "replace-with-a-dedicated-provider-encryption-key",
        }
        if self.app_env.lower() not in {"development", "dev", "local", "test"}:
            if self.provider_master_key in insecure_provider_keys:
                raise ValueError("PROVIDER_MASTER_KEY must be set to a dedicated production key")
            if not all(
                (
                    self.smtp_host,
                    self.smtp_username,
                    self.smtp_password,
                    self.smtp_from_email,
                )
            ):
                raise ValueError("Gmail SMTP settings are required outside development")
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
