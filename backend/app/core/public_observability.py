"""Public request telemetry without URLs, request bodies, embed keys or visitor identifiers."""

import logging
import time

import anyio
from redis.asyncio import Redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class PublicChatObservability:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        prefix = get_settings().api_v1_prefix + "/public/chatbots/"
        if scope["type"] != "http" or not scope.get("path", "").startswith(prefix):
            await self.app(scope, receive, send)
            return
        started = time.monotonic()
        status = 500

        async def observed_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, observed_send)
        finally:
            elapsed = round((time.monotonic() - started) * 1000)
            state = scope.get("state", {})
            code = state.get("public_error_code", "none")
            logger.info(
                "public_request request_id=%s chatbot_id=%s method=%s "
                "status=%s code=%s latency_ms=%s",
                state.get("request_id", "unknown"),
                state.get("public_chatbot_id", "unknown"),
                scope["method"],
                status,
                code,
                elapsed,
            )
            with anyio.CancelScope(shield=True):
                try:
                    async with Redis.from_url(
                        get_settings().redis_url,
                        socket_connect_timeout=1,
                        socket_timeout=1,
                    ) as redis:
                        async with redis.pipeline(transaction=True) as pipeline:
                            pipeline.hincrby("public:metrics", "requests", 1)
                            pipeline.hincrby("public:metrics", f"status:{status}", 1)
                            pipeline.hincrby("public:metrics", f"code:{code}", 1)
                            pipeline.hincrby("public:metrics", "latency_ms_sum", elapsed)
                            await pipeline.execute()
                except Exception:
                    logger.warning("Public metrics unavailable")
