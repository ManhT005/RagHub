"""CLI adapter for the shared, atomic installation use case."""

from pydantic import BaseModel, EmailStr, Field

from app.core.exceptions import AppError
from app.modules.installation.schemas import InitializeInstallationInput
from app.modules.installation.service import InitializeInstallationService


class BootstrapOwnerInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128, repr=False)
    organization_slug: str = Field(
        default="raghub", pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=100
    )
    organization_name: str = Field(default="RagHub", min_length=1, max_length=200)


async def bootstrap_owner(session, payload: BootstrapOwnerInput) -> dict[str, str]:
    try:
        result = await InitializeInstallationService(session).initialize(
            InitializeInstallationInput(
                owner_email=payload.email,
                owner_password=payload.password,
                organization_slug=payload.organization_slug,
                organization_name=payload.organization_name,
            ),
            allow_existing_owner=True,
        )
    except AppError as exc:
        raise ValueError(exc.message) from exc
    return {
        "user_id": result.user_id,
        "organization_id": result.organization_id,
        "email": result.email,
        "result": result.result,
    }
