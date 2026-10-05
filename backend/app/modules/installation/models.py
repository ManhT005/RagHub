import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class InstallationState(Base):
    __tablename__ = "installation_state"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_installation_singleton"),
        CheckConstraint(
            "status IN ('UNINITIALIZED', 'INITIALIZING', 'INITIALIZED')",
            name="ck_installation_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    status: Mapped[str] = mapped_column(String(32), default="UNINITIALIZED")
    installation_id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, unique=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL")
    )
    initialized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
