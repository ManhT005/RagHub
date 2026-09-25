import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Workspace(Base):
    __tablename__ = "workspaces"
    __table_args__ = (UniqueConstraint("organization_id", "slug", name="uq_workspaces_org_slug"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(100))
    embedding_provider_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("provider_configs.id", ondelete="SET NULL"), index=True
    )
    chat_provider_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("provider_configs.id", ondelete="SET NULL"), index=True
    )
    active_embedding_index_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("embedding_index_versions.id", ondelete="SET NULL"), index=True
    )
    pending_embedding_index_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("embedding_index_versions.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
