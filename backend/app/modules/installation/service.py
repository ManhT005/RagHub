from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.security import hash_password
from app.modules.auth.models import UserIdentity
from app.modules.auth.service import AuthResult, AuthService
from app.modules.installation.local_ai_bootstrap import (
    LocalAiBootstrapService,
    enqueue_local_ai_health,
)
from app.modules.installation.models import InstallationState
from app.modules.installation.schemas import InitializeInstallationInput
from app.modules.memberships.models import Membership
from app.modules.organizations.models import Organization
from app.modules.users.models import User


@dataclass(frozen=True)
class InstallationResult:
    user_id: str
    organization_id: str
    email: str
    result: str
    auth: AuthResult | None = None
    provider_ids: tuple[str, ...] = ()


class InitializeInstallationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def status(self) -> InstallationState:
        state = await self.session.get(InstallationState, 1)
        if state is None:
            raise AppError(
                "INSTALLATION_STATE_UNAVAILABLE", "Run database migrations.", status_code=503
            )
        return state

    async def initialize(
        self,
        payload: InitializeInstallationInput,
        *,
        auth_service: AuthService | None = None,
        allow_existing_owner: bool = False,
    ) -> InstallationResult:
        # This use case owns the transaction for both CLI and HTTP adapters.
        async with self.session.begin():
            state = await self.session.scalar(
                select(InstallationState).where(InstallationState.id == 1).with_for_update()
            )
            if state is None:
                raise AppError(
                    "INSTALLATION_STATE_UNAVAILABLE", "Run database migrations.", status_code=503
                )
            if state.status != "UNINITIALIZED":
                if allow_existing_owner and state.status == "INITIALIZED":
                    return await self._existing_owner(state, payload)
                raise AppError(
                    "INSTALLATION_ALREADY_INITIALIZED",
                    "Installation is already initialized.",
                    status_code=409,
                )
            state.status = "INITIALIZING"
            email = str(payload.owner_email).lower()
            if await self.session.scalar(select(User.id).where(func.lower(User.email) == email)):
                raise AppError(
                    "SETUP_IDENTITY_CONFLICT",
                    "Existing account cannot be adopted.",
                    status_code=409,
                )
            if await self.session.scalar(
                select(Organization.id).where(Organization.slug == payload.organization_slug)
            ):
                raise AppError(
                    "SETUP_ORGANIZATION_CONFLICT", "Organization already exists.", status_code=409
                )
            now = datetime.now(UTC)
            user = User(email=email, status="ACTIVE", email_verified_at=now)
            organization = Organization(
                name=payload.organization_name, slug=payload.organization_slug, status="ACTIVE"
            )
            self.session.add_all([user, organization])
            await self.session.flush()
            self.session.add_all(
                [
                    UserIdentity(
                        user_id=user.id,
                        provider="LOCAL",
                        provider_subject=email,
                        password_hash=hash_password(payload.owner_password),
                    ),
                    Membership(
                        user_id=user.id,
                        organization_id=organization.id,
                        role="ADMIN",
                        status="ACTIVE",
                    ),
                ]
            )
            provider_ids = []
            if payload.ai_mode == "LOCAL":
                models = await LocalAiBootstrapService(self.session).ensure(organization.id)
                provider_ids = [str(model.id) for model in models]
            auth = await auth_service.issue_session(user) if auth_service else None
            state.owner_id = user.id
            state.organization_id = organization.id
            state.status = "INITIALIZED"
            state.initialized_at = now
            await self.session.flush()
            result = InstallationResult(
                str(user.id), str(organization.id), email, "created", auth, tuple(provider_ids)
            )
        if provider_ids:
            import asyncio

            await asyncio.to_thread(enqueue_local_ai_health, result.organization_id, provider_ids)
        return result

    async def _existing_owner(self, state, payload) -> InstallationResult:
        user = await self.session.get(User, state.owner_id) if state.owner_id else None
        organization = (
            await self.session.get(Organization, state.organization_id)
            if state.organization_id
            else None
        )
        membership = (
            await self.session.get(Membership, (state.owner_id, state.organization_id))
            if user and organization
            else None
        )
        identity = (
            await self.session.scalar(
                select(UserIdentity).where(
                    UserIdentity.user_id == user.id, UserIdentity.provider == "LOCAL"
                )
            )
            if user
            else None
        )
        if (
            user is None
            or user.email.lower() != str(payload.owner_email).lower()
            or user.status != "ACTIVE"
            or not user.email_verified_at
            or organization is None
            or organization.slug != payload.organization_slug
            or organization.status != "ACTIVE"
            or membership is None
            or membership.role != "ADMIN"
            or membership.status != "ACTIVE"
            or identity is None
            or not identity.password_hash
        ):
            raise AppError(
                "INSTALLATION_ALREADY_INITIALIZED",
                "Existing account is not this installation's active owner.",
                status_code=409,
            )
        return InstallationResult(str(user.id), str(organization.id), user.email, "unchanged")
