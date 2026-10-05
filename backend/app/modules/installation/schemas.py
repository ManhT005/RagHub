from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class InitializeInstallationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    owner_email: EmailStr
    owner_password: str = Field(min_length=12, max_length=128, repr=False)
    organization_name: str = Field(default="RagHub", min_length=1, max_length=200)
    organization_slug: str = Field(
        default="raghub", pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=100
    )
    ai_mode: Literal["SKIP", "LOCAL"] = "SKIP"

    @field_validator("organization_name")
    @classmethod
    def organization_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Organization name cannot be blank")
        return value.strip()


class SetupStatusResponse(BaseModel):
    status: Literal["UNINITIALIZED", "INITIALIZING", "INITIALIZED"]
    initialized: bool


class InitializeInstallationResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    organization_id: str
    provider_ids: list[str] = Field(default_factory=list)
