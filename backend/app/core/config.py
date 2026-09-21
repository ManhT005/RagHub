from functools import lru_cache

from pydantic import Field
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
    api_v1_prefix: str = "/api/v1"
    max_upload_size_mb: int = Field(default=25, ge=1, le=500)

    database_url: str = "postgresql+asyncpg://raghub:raghub-local-only@localhost:5432/raghub"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_index: str = "raghub_chunks_v1"
    elasticsearch_alias: str = "raghub_chunks_current"

    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "raghub"
    s3_secret_key: str = "raghub-local-only"
    s3_bucket: str = "raghub-documents"
    s3_secure: bool = False

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def sqlalchemy_sync_url(self) -> str:
        return self.database_url.replace("+asyncpg", "+psycopg")


@lru_cache
def get_settings() -> Settings:
    return Settings()
