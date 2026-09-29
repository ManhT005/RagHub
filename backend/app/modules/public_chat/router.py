import asyncio
import json
import logging
from contextlib import suppress
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, status
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.exceptions import AppError
from app.core.redis import get_redis
from app.modules.chatbots.models import Conversation
from app.modules.chatbots.service import ChatbotService
from app.modules.public_chat.client_ip import resolve_client_ip
from app.modules.public_chat.concurrency import ConcurrencyLimiter
from app.modules.public_chat.rate_limit import FixedWindowRateLimiter
from app.modules.public_chat.schemas import (
    PublicChatRequest,
    PublicConfigResponse,
    PublicConversationInput,
    PublicConversationResponse,
)
from app.modules.public_chat.service import PublicChatAccessService, cors_headers

router = APIRouter(prefix="/public/chatbots", tags=["public-chat"])
logger = logging.getLogger(__name__)


def _attach_cors_to_error(exc: AppError, headers: dict[str, str]) -> None:
    exc.headers.update(headers)


async def _access(
    public_key: str,
    session: AsyncSession,
    origin: str | None,
    api_key: str | None,
):
    service = PublicChatAccessService(session)
    chatbot = await service.resolve(public_key)
    return await service.authorize(chatbot, origin, api_key)


@router.options("/{public_key}/{action}", status_code=status.HTTP_204_NO_CONTENT)
async def preflight(
    public_key: str,
    action: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    origin: Annotated[str | None, Header(alias="Origin")] = None,
) -> Response:
    if action not in {"config", "conversations", "chat"} or origin is None:
        raise AppError("PUBLIC_ACCESS_DENIED", "A valid origin is required.", status_code=403)
    context = await _access(public_key, session, origin, None)
    return Response(status_code=204, headers=cors_headers(context))


@router.get("/{public_key}/config", response_model=PublicConfigResponse)
async def public_config(
    public_key: str,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    origin: Annotated[str | None, Header(alias="Origin")] = None,
    api_key: Annotated[str | None, Header(alias="X-RagHub-API-Key")] = None,
) -> PublicConfigResponse:
    context = await _access(public_key, session, origin, api_key)
    response.headers.update(cors_headers(context))
    response.headers["Cache-Control"] = "no-store"
    return PublicConfigResponse(
        public_key=public_key,
        name=context.chatbot.name,
        capabilities={"streaming": True, "citations": True},
        limits={"message_max_length": 4_000},
    )


@router.post(
    "/{public_key}/conversations",
    response_model=PublicConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_public_conversation(
    public_key: str,
    payload: PublicConversationInput,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    settings: Annotated[Settings, Depends(get_settings)],
    origin: Annotated[str | None, Header(alias="Origin")] = None,
    api_key: Annotated[str | None, Header(alias="X-RagHub-API-Key")] = None,
) -> PublicConversationResponse:
    del payload
    context = await _access(public_key, session, origin, api_key)
    cors = cors_headers(context)
    try:
        await FixedWindowRateLimiter(redis).consume(
            "public-conversation",
            context.chatbot_id,
            resolve_client_ip(request, settings),
            settings.public_conversation_rate_limit_requests,
            settings.public_conversation_rate_limit_window_seconds,
        )
    except AppError as exc:
        _attach_cors_to_error(exc, cors)
        raise
    conversation = Conversation(chatbot_id=context.chatbot_id, external_user_id=None)
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    response.headers.update(cors)
    return PublicConversationResponse(conversation_id=conversation.id)


@router.post("/{public_key}/chat")
async def public_chat(
    public_key: str,
    payload: PublicChatRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    settings: Annotated[Settings, Depends(get_settings)],
    origin: Annotated[str | None, Header(alias="Origin")] = None,
    api_key: Annotated[str | None, Header(alias="X-RagHub-API-Key")] = None,
) -> StreamingResponse:
    context = await _access(public_key, session, origin, api_key)
    cors = cors_headers(context)
    try:
        await FixedWindowRateLimiter(redis).consume(
            "public-chat",
            context.chatbot_id,
            resolve_client_ip(request, settings),
            settings.public_chat_rate_limit_requests,
            settings.public_chat_rate_limit_window_seconds,
        )
    except AppError as exc:
        _attach_cors_to_error(exc, cors)
        raise
    limiter = ConcurrencyLimiter(redis)
    try:
        lease = await limiter.acquire(
            context.chatbot_id,
            context.organization_id,
            settings.public_chat_max_concurrent_per_chatbot,
            settings.public_chat_max_concurrent_per_org,
            settings.public_chat_concurrency_lease_seconds,
        )
    except AppError as exc:
        _attach_cors_to_error(exc, cors)
        raise

    async def events():
        stop_heartbeat = asyncio.Event()
        stream_task = asyncio.current_task()

        async def heartbeat() -> None:
            interval = max(1.0, settings.public_chat_concurrency_lease_seconds / 3)
            while not stop_heartbeat.is_set():
                try:
                    await asyncio.wait_for(stop_heartbeat.wait(), timeout=interval)
                    return
                except TimeoutError:
                    try:
                        renewed = await limiter.renew(
                            lease, settings.public_chat_concurrency_lease_seconds
                        )
                        if not renewed:
                            raise RuntimeError("Public chat concurrency lease no longer exists")
                    except Exception:
                        logger.exception("Failed to renew public chat concurrency lease")
                        if stream_task is not None:
                            stream_task.cancel()
                        return

        heartbeat_task = asyncio.create_task(heartbeat())
        try:
            try:
                async for event, data in ChatbotService(session).stream(
                    context.organization_id,
                    context.chatbot_id,
                    payload.message,
                    payload.conversation_id,
                    None,
                ):
                    yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
            except AppError as exc:
                error = {"code": exc.code, "message": exc.message}
                yield f"event: error\ndata: {json.dumps(error)}\n\n"
            except Exception:
                logger.exception("Unexpected public chat stream error")
                error = {"code": "INTERNAL_ERROR", "message": "The chat stream failed."}
                yield f"event: error\ndata: {json.dumps(error)}\n\n"
        finally:
            stop_heartbeat.set()
            heartbeat_task.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat_task
            await asyncio.shield(limiter.release(lease))

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    headers.update(cors)
    return StreamingResponse(events(), media_type="text/event-stream", headers=headers)
