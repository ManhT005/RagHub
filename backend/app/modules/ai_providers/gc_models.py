"""Index GC audit records."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class IndexGcRun(Base):
    __tablename__ = "index_gc_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    mode: Mapped[str] = mapped_column(String(16))
    policy_version: Mapped[str] = mapped_column(String(32), default="v1")
    correlation_id: Mapped[str | None] = mapped_column(String(128))
    candidates: Mapped[int] = mapped_column(Integer, default=0)
    deletions: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IndexGcItem(Base):
    __tablename__ = "index_gc_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("index_gc_runs.id", ondelete="CASCADE"), index=True
    )
    index_name: Mapped[str] = mapped_column(String(255))
    version_id: Mapped[uuid.UUID | None] = mapped_column()
    state: Mapped[str] = mapped_column(String(32), default="unknown")
    age_hours: Mapped[float | None] = mapped_column(Float)
    decision: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(255), default="")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
