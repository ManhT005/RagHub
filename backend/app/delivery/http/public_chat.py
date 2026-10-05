import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import aclosing

import anyio
from fastapi import Request
from fastapi.responses import StreamingResponse

from app.delivery.http.sse import serialize_event, stream_sse
from raghub_core.domain.rag.events import ChatFailed, RagEvent

logger = logging.getLogger(__name__)


async def public_stream_sse(
    events: AsyncIterator[RagEvent],
    request: Request,
    *,
    timeout_seconds: float,
) -> AsyncIterator[str]:
    def record_error(error: ChatFailed) -> None:
        request.state.public_error_code = error.code

    try:
        async with (
            asyncio.timeout(timeout_seconds),
            aclosing(stream_sse(events, on_error=record_error)) as stream,
        ):
            async for frame in stream:
                yield frame
    except TimeoutError:
        error = ChatFailed("PUBLIC_CHAT_TIMEOUT", "Chat timed out.")
        record_error(error)
        yield serialize_event(error)


class PublicStreamingResponse(StreamingResponse):
    def __init__(self, *args, limits, chatbot_id, slot, **kwargs):
        super().__init__(*args, **kwargs)
        self.limits, self.chatbot_id, self.slot = limits, chatbot_id, slot

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
                    try:
                        await self.limits.release(self.chatbot_id, self.slot)
                    except Exception:
                        logger.warning("Public slot release failed chatbot_id=%s", self.chatbot_id)
