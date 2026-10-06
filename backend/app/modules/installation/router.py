from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.core.config import Settings, get_settings
from app.modules.auth.cookies import set_refresh_cookie
from app.modules.auth.dependencies import get_auth_service
from app.modules.auth.service import AuthService
from app.modules.installation.dependencies import get_installation_service
from app.modules.installation.schemas import (
    InitializeInstallationInput,
    InitializeInstallationResponse,
    SetupStatusResponse,
)
from app.modules.installation.service import InitializeInstallationService

router = APIRouter(prefix="/setup", tags=["setup"])


@router.get("/status", response_model=SetupStatusResponse)
async def setup_status(
    response: Response,
    service: Annotated[InitializeInstallationService, Depends(get_installation_service)],
) -> SetupStatusResponse:
    state = await service.status()
    response.headers["Cache-Control"] = "no-store"
    return SetupStatusResponse(status=state.status, initialized=state.status == "INITIALIZED")


@router.post("/initialize", response_model=InitializeInstallationResponse, status_code=201)
async def initialize(
    payload: InitializeInstallationInput,
    response: Response,
    service: Annotated[InitializeInstallationService, Depends(get_installation_service)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> InitializeInstallationResponse:
    result = await service.initialize(payload, auth_service=auth)
    token = set_refresh_cookie(response, result.auth, settings)
    response.headers["Cache-Control"] = "no-store"
    return InitializeInstallationResponse(
        access_token=token.access_token,
        user_id=result.user_id,
        organization_id=result.organization_id,
        provider_ids=list(result.provider_ids),
    )
