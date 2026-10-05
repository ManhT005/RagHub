import uuid
from datetime import datetime
from typing import Any

from raghub_core.domain.providers.enums import IndexVersionStatus, ReindexJobStatus
from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ProviderConnection(Base):
    __tablename__ = "provider_connections"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    provider_type: Mapped[str] = mapped_column(String(64))
    catalog_id: Mapped[str | None] = mapped_column(String(100))
    base_url: Mapped[str | None] = mapped_column(String(1024))
    encrypted_secret: Mapped[str | None] = mapped_column(Text)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(default=True)
    status: Mapped[str] = mapped_column(String(32), default="UNTESTED", server_default="UNTESTED")
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_latency_ms: Mapped[int | None] = mapped_column(Integer)
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProviderConfig(Base):
    __tablename__ = "provider_configs"
    __table_args__ = (Index("ix_provider_configs_org_capability", "organization_id", "capability"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("provider_connections.id", ondelete="RESTRICT"), index=True
    )
    connection: Mapped[ProviderConnection | None] = relationship(lazy="joined")
    display_name: Mapped[str | None] = mapped_column(String(200))
    availability_status: Mapped[str] = mapped_column(
        String(32), default="UNTESTED", server_default="UNTESTED"
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, server_default="{}")
    last_health_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    provider_type: Mapped[str] = mapped_column(String(64))
    capability: Mapped[str] = mapped_column(String(32))
    base_url: Mapped[str | None] = mapped_column(String(1024))
    model: Mapped[str] = mapped_column(String(255))
    dimension: Mapped[int | None] = mapped_column(Integer)
    encrypted_secret: Mapped[str | None] = mapped_column(Text)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EmbeddingIndexVersion(Base):
    __tablename__ = "embedding_index_versions"
    __table_args__ = (
        Index("ix_embedding_index_versions_workspace_status", "workspace_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    provider_config_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("provider_configs.id", ondelete="RESTRICT"), index=True
    )
    provider_type: Mapped[str] = mapped_column(String(64))
    base_url: Mapped[str | None] = mapped_column(String(1024))
    model: Mapped[str] = mapped_column(String(255))
    dimension: Mapped[int] = mapped_column(Integer)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    embedding_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    index_name: Mapped[str] = mapped_column(String(255), unique=True)
    status: Mapped[str] = mapped_column(String(32), default=IndexVersionStatus.BUILDING)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OllamaModelPull(Base):
    __tablename__ = "ollama_model_pulls"
    __table_args__ = (
        Index(
            "ix_ollama_pull_active_connection",
            "connection_id",
            unique=True,
            postgresql_where=text("status IN ('QUEUED', 'PULLING', 'VERIFYING')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("provider_connections.id", ondelete="CASCADE"), index=True
    )
    model: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="QUEUED")
    register_after_pull: Mapped[bool] = mapped_column(default=True)
    completed_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    total_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    error_code: Mapped[str | None] = mapped_column(String(100))
    registered_model_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("provider_configs.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EmbeddingReindexJob(Base):
    __tablename__ = "embedding_reindex_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    target_index_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("embedding_index_versions.id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[str] = mapped_column(String(32), default=ReindexJobStatus.QUEUED)
    total_documents: Mapped[int] = mapped_column(Integer, default=0)
    processed_documents: Mapped[int] = mapped_column(Integer, default=0)
    failed_documents: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
