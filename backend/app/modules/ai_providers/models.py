import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.modules.ai_providers.enums import IndexVersionStatus, ReindexJobStatus


class ProviderConfig(Base):
    __tablename__ = "provider_configs"
    __table_args__ = (Index("ix_provider_configs_org_capability", "organization_id", "capability"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
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
    model: Mapped[str] = mapped_column(String(255))
    dimension: Mapped[int] = mapped_column(Integer)
    embedding_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    index_name: Mapped[str] = mapped_column(String(255), unique=True)
    status: Mapped[str] = mapped_column(String(32), default=IndexVersionStatus.BUILDING)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
