import asyncio
import json
import logging
from contextlib import aclosing
from typing import Annotated
from uuid import UUID

import anyio
from fastapi import APIRouter, Depends, Header, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    OrganizationContext,
    get_current_user,
    get_organization_context,
    require_role,
)
from app.core.database import get_session
from app.core.exceptions import AppError
from app.modules.chatbots.public_limits import PublicChatLimits, client_ip, get_public_limits
from app.modules.chatbots.schemas import (
    ChatbotInput,
    ChatbotPatch,
    ChatbotResponse,
    ChatRequest,
    EmbedCodeResponse,
    EmbedPublishInput,
)
from app.modules.chatbots.service import ChatbotService
from app.modules.memberships.models import MembershipRole
from app.modules.users.models import User

router = APIRouter(tags=["chatbots"])
logger = logging.getLogger(__name__)


class PublicStreamingResponse(StreamingResponse):
    def __init__(self, *args, limits, chatbot_id, slot, **kwargs):
        super().__init__(*args, **kwargs)
        self.limits = limits
        self.chatbot_id = chatbot_id
        self.slot = slot

    async def __call__(self, scope, receive, send):
        try:
            # Also bound slow network sends, which the generator deadline cannot cancel.
            with anyio.move_on_after(self.limits.settings.public_chat_stream_timeout_seconds + 1):
                await super().__call__(scope, receive, send)
        finally:
            # Starlette cancels the stream task on disconnect. Cleanup must survive it.
            with anyio.CancelScope(shield=True):
                try:
                    await self.body_iterator.aclose()
                finally:
                    await self._release_slot()

    async def _release_slot(self):
        try:
            await self.limits.release(self.chatbot_id, self.slot)
        except Exception:
            logger.warning("Public slot release failed chatbot_id=%s", self.chatbot_id)


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


@router.post("/chatbots/{chatbot_id}/publish", response_model=EmbedCodeResponse)
async def publish_embed(
    chatbot_id: UUID,
    payload: EmbedPublishInput,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EmbedCodeResponse:
    require_role(context, MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.EDITOR)
    _, key = await ChatbotService(session).publish_embed(
        context.organization_id, chatbot_id, payload
    )
    if key is None:
        raise AppError(
            "EMBED_KEY_ALREADY_EXISTS",
            "Use the embed-code endpoint or rotate the key.",
            status_code=409,
        )
    return EmbedCodeResponse(
        code=f'<script src="/widget/raghub.js" data-chatbot-key="{key}" async></script>', key=key
    )


@router.post("/chatbots/{chatbot_id}/embed-key/rotate", response_model=EmbedCodeResponse)
async def rotate_embed_key(
    chatbot_id: UUID,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EmbedCodeResponse:
    require_role(context, MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.EDITOR)
    key = await ChatbotService(session).rotate_embed_key(context.organization_id, chatbot_id)
    return EmbedCodeResponse(
        code=f'<script src="/widget/raghub.js" data-chatbot-key="{key}" async></script>', key=key
    )


@router.get("/chatbots/{chatbot_id}/embed-code", response_model=EmbedCodeResponse)
async def embed_code(
    chatbot_id: UUID,
    context: Annotated[OrganizationContext, Depends(get_organization_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EmbedCodeResponse:
    chatbot = await ChatbotService(session).get(context.organization_id, chatbot_id)
    if not chatbot.published or not chatbot.embed_key_hash:
        raise AppError(
            "EMBED_NOT_PUBLISHED",
            "Publish this chatbot before copying its embed code.",
            status_code=409,
        )
    return EmbedCodeResponse(
        code='<script src="/widget/raghub.js" data-chatbot-key="REDACTED" async></script>'
    )


@router.get("/public/chatbots/{embed_key}/config")
async def public_config(
    embed_key: str,
    origin: Annotated[str | None, Header()] = None,
    session: Annotated[AsyncSession, Depends(get_session)] = None,
) -> JSONResponse:
    config = await ChatbotService(session).public_config(embed_key, origin)
    return JSONResponse(config, headers=public_cors_headers(origin))


def public_cors_headers(origin: str | None) -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": origin or "",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Vary": "Origin",
    }


@router.options("/public/chatbots/{embed_key}/chat", status_code=status.HTTP_204_NO_CONTENT)
async def public_chat_options(
    embed_key: str,
    origin: Annotated[str | None, Header()] = None,
    session: Annotated[AsyncSession, Depends(get_session)] = None,
) -> Response:
    await ChatbotService(session).public_chatbot(embed_key, origin)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=public_cors_headers(origin))


@router.post("/public/chatbots/{embed_key}/chat")
async def public_chat(
    embed_key: str,
    payload: ChatRequest,
    request: Request,
    origin: Annotated[str | None, Header()] = None,
    session: Annotated[AsyncSession, Depends(get_session)] = None,
    limits: Annotated[PublicChatLimits, Depends(get_public_limits)] = None,
) -> StreamingResponse:
    chatbot = await ChatbotService(session).public_chatbot(embed_key, origin)
    request.state.public_origin = origin
    request.state.public_chatbot_id = str(chatbot.id)
    await limits.check_rate(str(chatbot.id), client_ip(request, limits.settings))
    slot = await limits.acquire(str(chatbot.id))

    async def events():
        try:
            async with (
                asyncio.timeout(limits.settings.public_chat_stream_timeout_seconds),
                aclosing(
                    ChatbotService(session).stream(
                        chatbot.organization_id,
                        chatbot.id,
                        payload.message,
                        payload.conversation_id,
                        payload.external_user_id,
                    )
                ) as stream,
            ):
                async for event, data in stream:
                    yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        except TimeoutError:
            request.state.public_error_code = "PUBLIC_CHAT_TIMEOUT"
            error = {"code": "PUBLIC_CHAT_TIMEOUT", "message": "Chat timed out."}
            yield f"event: error\ndata: {json.dumps(error)}\n\n"
        except AppError as exc:
            request.state.public_error_code = exc.code
            error = {"code": exc.code, "message": exc.message}
            yield f"event: error\ndata: {json.dumps(error)}\n\n"

    return PublicStreamingResponse(
        events(),
        limits=limits,
        chatbot_id=str(chatbot.id),
        slot=slot,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            **public_cors_headers(origin),
        },
    )


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
