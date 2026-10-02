"""Organization-scoped user administration for ADMIN members."""

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import OrganizationContext, get_organization_context, require_role
from app.core.database import get_session
from app.core.exceptions import AppError
from app.core.security import hash_password
from app.modules.auth.models import IdentityProvider, UserIdentity, UserSession
from app.modules.memberships.models import Membership, MembershipRole, WorkspaceMembership
from app.modules.users.models import User
from app.modules.workspaces.models import Workspace

router = APIRouter(prefix="/admin", tags=["admin"])


class AdminUserWorkspace(BaseModel):
    id: UUID
    name: str
    slug: str


class AdminUserItem(BaseModel):
    id: UUID
    email: str
    display_name: str | None = None
    status: str
    last_login_at: datetime | None = None
    created_at: datetime | None = None
    role: MembershipRole
    workspace_ids: list[UUID] = Field(default_factory=list)
    workspaces: list[AdminUserWorkspace] = Field(default_factory=list)


class AdminUserPage(BaseModel):
    items: list[AdminUserItem]
    page: int
    page_size: int
    total: int


class AdminUserCreateInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=200)


class AdminUserUpdateInput(BaseModel):
    display_name: str | None = Field(default=None, max_length=200)


class AdminUserStatusInput(BaseModel):
    status: Literal["ACTIVE", "DISABLED"]


async def _workspace_map(
    session: AsyncSession, user_ids: list[UUID], organization_id: UUID
) -> dict[UUID, list[AdminUserWorkspace]]:
    if not user_ids:
        return {}
    rows = await session.execute(
        select(WorkspaceMembership.user_id, Workspace.id, Workspace.name, Workspace.slug)
        .join(Workspace, Workspace.id == WorkspaceMembership.workspace_id)
        .where(
            WorkspaceMembership.user_id.in_(user_ids),
            Workspace.organization_id == organization_id,
            Workspace.deleted_at.is_(None),
        )
        .order_by(Workspace.name)
    )
    grouped: dict[UUID, list[AdminUserWorkspace]] = {user_id: [] for user_id in user_ids}
    for user_id, workspace_id, name, slug in rows:
        grouped[user_id].append(AdminUserWorkspace(id=workspace_id, name=name, slug=slug))
    return grouped


def _item(user: User, role: MembershipRole, workspaces: list[AdminUserWorkspace]) -> AdminUserItem:
    return AdminUserItem(
        id=user.id,
        email=user.email,
        display_name=getattr(user, "display_name", None),
        status=user.status,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        role=role,
        workspace_ids=[workspace.id for workspace in workspaces],
        workspaces=workspaces,
    )


@router.get("/users", response_model=AdminUserPage)
async def list_admin_users(
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
    q: Annotated[str, Query(max_length=320)] = "",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 10,
) -> AdminUserPage:
    require_role(context, MembershipRole.ADMIN)
    keyword = q.strip().lower()
    filters = [Membership.organization_id == context.organization_id]
    if keyword:
        filters.append(
            func.lower(User.email).like(f"%{keyword}%")
            | func.lower(User.display_name).like(f"%{keyword}%")
        )
    total = await session.scalar(
        select(func.count())
        .select_from(Membership)
        .join(User, User.id == Membership.user_id)
        .where(*filters)
    )
    rows = await session.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(*filters)
        .order_by(User.email)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    pairs = list(rows)
    workspace_map = await _workspace_map(
        session, [user.id for _, user in pairs], context.organization_id
    )
    return AdminUserPage(
        items=[
            _item(user, membership.role, workspace_map.get(user.id, []))
            for membership, user in pairs
        ],
        page=page,
        page_size=page_size,
        total=total or 0,
    )


@router.post("/users", response_model=AdminUserItem, status_code=201)
async def create_admin_user(
    payload: AdminUserCreateInput,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AdminUserItem:
    require_role(context, MembershipRole.ADMIN)
    email = payload.email.strip().lower()
    existing = await session.scalar(select(User.id).where(func.lower(User.email) == email))
    if existing is not None:
        raise AppError("USER_EMAIL_TAKEN", "This email is already registered.", status_code=409)
    now = datetime.now(UTC)
    display_name = (payload.display_name or "").strip() or None
    user = User(
        id=uuid4(),
        email=email,
        display_name=display_name,
        status="ACTIVE",
        email_verified_at=now,
        created_at=now,
    )
    session.add(user)
    await session.flush()
    session.add(
        UserIdentity(
            id=uuid4(),
            user_id=user.id,
            provider=IdentityProvider.LOCAL,
            provider_subject=email,
            password_hash=hash_password(payload.password),
        )
    )
    membership = Membership(
        user_id=user.id,
        organization_id=context.organization_id,
        role=MembershipRole.WORKSPACE_ADMIN,
    )
    session.add(membership)
    await session.commit()
    await session.refresh(user)
    return _item(user, membership.role, [])


@router.patch("/users/{user_id}", response_model=AdminUserItem)
async def update_admin_user(
    user_id: UUID,
    payload: AdminUserUpdateInput,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AdminUserItem:
    require_role(context, MembershipRole.ADMIN)
    membership = await session.get(Membership, (user_id, context.organization_id))
    if membership is None:
        raise AppError("USER_NOT_FOUND", "User was not found.", status_code=404)
    user = await session.get(User, user_id)
    if user is None:
        raise AppError("USER_NOT_FOUND", "User was not found.", status_code=404)
    user.display_name = (payload.display_name or "").strip() or None
    await session.commit()
    await session.refresh(user)
    workspace_map = await _workspace_map(session, [user.id], context.organization_id)
    return _item(user, membership.role, workspace_map.get(user.id, []))


@router.patch("/users/{user_id}/status", response_model=AdminUserItem)
async def update_admin_user_status(
    user_id: UUID,
    payload: AdminUserStatusInput,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AdminUserItem:
    require_role(context, MembershipRole.ADMIN)
    membership = await session.get(Membership, (user_id, context.organization_id))
    if membership is None:
        raise AppError("USER_NOT_FOUND", "User was not found.", status_code=404)
    user = await session.get(User, user_id)
    if user is None:
        raise AppError("USER_NOT_FOUND", "User was not found.", status_code=404)
    if user_id == context.membership.user_id and payload.status == "DISABLED":
        raise AppError(
            "SELF_DISABLE_NOT_ALLOWED",
            "You cannot disable your own account.",
            status_code=409,
        )
    now = datetime.now(UTC)
    if payload.status == "DISABLED":
        user.status = "DISABLED"
        user.auth_version += 1
        await session.execute(
            update(UserSession)
            .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
    else:
        user.status = "ACTIVE"
    await session.commit()
    await session.refresh(user)
    workspace_map = await _workspace_map(session, [user.id], context.organization_id)
    workspaces = workspace_map.get(user.id, [])
    return _item(user, membership.role, workspaces)
