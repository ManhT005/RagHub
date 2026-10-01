"""One pooled Redis client per ASGI application lifespan."""

from contextlib import asynccontextmanager

import anyio
from fastapi import FastAPI, Request
from redis.asyncio import Redis

from app.core.config import get_settings


@asynccontextmanager
async def redis_lifespan(app: FastAPI):
    redis = Redis.from_url(
        get_settings().redis_url,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    app.state.redis = redis
    try:
        yield
    finally:
        # ASGI shutdown follows response cleanup, including cancelled SSE streams.
        with anyio.CancelScope(shield=True):
            try:
                await redis.aclose()
            finally:
                del app.state.redis


def get_redis(request: Request) -> Redis:
    return request.app.state.redis
