import uuid
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MembershipRole(StrEnum):
    ADMIN = "ADMIN"
    WORKSPACE_ADMIN = "WORKSPACE_ADMIN"


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'DISABLED')", name="ck_memberships_status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(32), default=MembershipRole.ADMIN)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", server_default="ACTIVE")


class WorkspaceMembership(Base):
    __tablename__ = "workspace_memberships"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )


class WorkspaceMembershipPermission(Base):
    __tablename__ = "workspace_membership_permissions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "workspace_id"],
            ["workspace_memberships.user_id", "workspace_memberships.workspace_id"],
            ondelete="CASCADE",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    permission: Mapped[str] = mapped_column(String(64), primary_key=True)
