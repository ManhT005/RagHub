import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    OrganizationContext,
    get_current_user,
    get_organization_context,
    require_role,
)
from app.core.database import get_session
from app.core.exceptions import AppError
from app.modules.chatbots.schemas import ChatbotInput, ChatbotPatch, ChatbotResponse, ChatRequest
from app.modules.chatbots.service import ChatbotService
from app.modules.memberships.models import MembershipRole
from app.modules.users.models import User

router = APIRouter(tags=["chatbots"])


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
