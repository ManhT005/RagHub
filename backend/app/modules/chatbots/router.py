import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    OrganizationContext,
    get_current_user,
    get_organization_context,
    require_role,
)
from app.core.database import get_session
from app.core.exceptions import AppError
from app.modules.chatbots.models import ChatbotAllowedOrigin
from app.modules.chatbots.schemas import ChatbotInput, ChatbotPatch, ChatbotResponse, ChatRequest
from app.modules.chatbots.service import ChatbotService
from app.modules.memberships.models import MembershipRole
from app.modules.public_chat.api_keys import ApiKeyService
from app.modules.public_chat.origin import require_valid_origin
from app.modules.public_chat.schemas import (
    AllowedOriginsInput,
    AllowedOriginsResponse,
    ApiKeyCreate,
    ApiKeyCreatedResponse,
    ApiKeyResponse,
)
from app.modules.users.models import User

router = APIRouter(tags=["chatbots"])


def api_key_response(row: object, *, raw_key: str | None = None):
    values = {
        "id": row.id,
        "name": row.name,
        "prefix": row.key_prefix,
        "created_at": row.created_at,
        "expires_at": row.expires_at,
        "revoked_at": row.revoked_at,
        "last_used_at": row.last_used_at,
    }
    if raw_key is not None:
        return ApiKeyCreatedResponse(**values, api_key=raw_key)
    return ApiKeyResponse(**values)


def response(chatbot: object) -> ChatbotResponse:
    return ChatbotResponse.model_validate(chatbot, from_attributes=True)


@router.get("/workspaces/{workspace_id}/chatbots", response_model=list[ChatbotResponse])
async def list_chatbots(
    workspace_id: UUID,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ChatbotResponse]:
    return [
        response(item)
        for item in await ChatbotService(session).list(context.organization_id, workspace_id)
    ]


@router.post(
    "/workspaces/{workspace_id}/chatbots",
    response_model=ChatbotResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_chatbot(
    workspace_id: UUID,
    payload: ChatbotInput,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ChatbotResponse:
    require_role(context, MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.EDITOR)
    return response(
        await ChatbotService(session).create(context.organization_id, workspace_id, payload)
    )


@router.get("/chatbots/{chatbot_id}", response_model=ChatbotResponse)
async def get_chatbot(
    chatbot_id: UUID,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ChatbotResponse:
    return response(await ChatbotService(session).get(context.organization_id, chatbot_id))


@router.patch("/chatbots/{chatbot_id}", response_model=ChatbotResponse)
async def patch_chatbot(
    chatbot_id: UUID,
    payload: ChatbotPatch,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ChatbotResponse:
    require_role(context, MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.EDITOR)
    return response(
        await ChatbotService(session).update(context.organization_id, chatbot_id, payload)
    )


@router.delete("/chatbots/{chatbot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chatbot(
    chatbot_id: UUID,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    require_role(context, MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.EDITOR)
    await ChatbotService(session).delete(context.organization_id, chatbot_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/chatbots/{chatbot_id}/allowed-origins", response_model=AllowedOriginsResponse
)
async def list_allowed_origins(
    chatbot_id: UUID,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AllowedOriginsResponse:
    await ChatbotService(session).get(context.organization_id, chatbot_id)
    origins = list(
        await session.scalars(
            select(ChatbotAllowedOrigin.origin)
            .where(ChatbotAllowedOrigin.chatbot_id == chatbot_id)
            .order_by(ChatbotAllowedOrigin.origin)
        )
    )
    return AllowedOriginsResponse(origins=origins)


@router.put(
    "/chatbots/{chatbot_id}/allowed-origins", response_model=AllowedOriginsResponse
)
async def replace_allowed_origins(
    chatbot_id: UUID,
    payload: AllowedOriginsInput,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AllowedOriginsResponse:
    require_role(context, MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.EDITOR)
    await ChatbotService(session).get(context.organization_id, chatbot_id)
    origins = sorted({require_valid_origin(value.strip()) for value in payload.origins})
    await session.execute(
        delete(ChatbotAllowedOrigin).where(ChatbotAllowedOrigin.chatbot_id == chatbot_id)
    )
    session.add_all(
        [ChatbotAllowedOrigin(chatbot_id=chatbot_id, origin=origin) for origin in origins]
    )
    await session.commit()
    return AllowedOriginsResponse(origins=origins)


@router.get("/chatbots/{chatbot_id}/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    chatbot_id: UUID,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ApiKeyResponse]:
    require_role(context, MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.EDITOR)
    await ChatbotService(session).get(context.organization_id, chatbot_id)
    rows = await ApiKeyService(session).list(context.organization_id, chatbot_id)
    return [api_key_response(row) for row in rows]


@router.post(
    "/chatbots/{chatbot_id}/api-keys",
    response_model=ApiKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key(
    chatbot_id: UUID,
    payload: ApiKeyCreate,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ApiKeyCreatedResponse:
    require_role(context, MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.EDITOR)
    await ChatbotService(session).get(context.organization_id, chatbot_id)
    row, raw_key = await ApiKeyService(session).create(
        context.organization_id, chatbot_id, payload.name, payload.expires_at
    )
    return api_key_response(row, raw_key=raw_key)


@router.post("/chatbots/{chatbot_id}/api-keys/{key_id}/revoke", response_model=ApiKeyResponse)
async def revoke_api_key(
    chatbot_id: UUID,
    key_id: UUID,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ApiKeyResponse:
    require_role(context, MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.EDITOR)
    await ChatbotService(session).get(context.organization_id, chatbot_id)
    row = await ApiKeyService(session).revoke(context.organization_id, chatbot_id, key_id)
    return api_key_response(row)


@router.post("/chatbots/{chatbot_id}/chat")
async def chat(
    chatbot_id: UUID,
    payload: ChatRequest,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StreamingResponse:
    async def events():
        try:
            async for event, data in ChatbotService(session).stream(
                context.organization_id,
                chatbot_id,
                payload.message,
                payload.conversation_id,
                str(user.id),
            ):
                yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        except AppError as exc:
            error = {"code": exc.code, "message": exc.message}
            yield f"event: error\ndata: {json.dumps(error)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
