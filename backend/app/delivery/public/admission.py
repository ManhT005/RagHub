from ipaddress import ip_address, ip_network
from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from starlette.requests import Request

from app.core.config import Settings, get_settings
from app.core.redis import get_redis
from app.infrastructure.redis.public_chat_admission import PublicChatLimits as PublicChatLimits


def client_ip(request: Request, settings: Settings) -> str:
    peer = request.client.host if request.client else "unknown"
    try:
        address = ip_address(peer)
        trusted = any(
            address in ip_network(cidr.strip())
            for cidr in settings.public_chat_trusted_proxy_cidrs.split(",")
            if cidr.strip()
        )
        if trusted:
            return str(ip_address(request.headers.get("x-real-ip", peer)))
    except ValueError:
        pass
    return peer


async def get_public_limits(
    redis: Annotated[Redis, Depends(get_redis)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PublicChatLimits:
    return PublicChatLimits(redis, settings)
