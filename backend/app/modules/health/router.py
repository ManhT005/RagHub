from typing import Annotated, Literal

import httpx
from elasticsearch import AsyncElasticsearch
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import SessionFactory
from app.core.exceptions import AppError
from app.core.redis import get_redis

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


@router.get("/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    return HealthResponse()


@router.get("/ready", response_model=HealthResponse)
async def readiness(redis: Annotated[Redis, Depends(get_redis)]) -> HealthResponse:
    settings = get_settings()
    failures: dict[str, str] = {}

    try:
        async with SessionFactory() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - exercised by deployment probes
        failures["postgres"] = type(exc).__name__

    try:
        await redis.ping()
    except Exception as exc:  # pragma: no cover - exercised by deployment probes
        failures["redis"] = type(exc).__name__

    elasticsearch = AsyncElasticsearch(settings.elasticsearch_url)
    try:
        if not await elasticsearch.ping():
            failures["elasticsearch"] = "unavailable"
    except Exception as exc:  # pragma: no cover - exercised by deployment probes
        failures["elasticsearch"] = type(exc).__name__
    finally:
        await elasticsearch.close()

    try:
        async with httpx.AsyncClient(timeout=2) as client:
            response = await client.get(f"{settings.s3_endpoint}/minio/health/ready")
            response.raise_for_status()
    except Exception as exc:  # pragma: no cover - exercised by deployment probes
        failures["minio"] = type(exc).__name__

    if failures:
        raise AppError(
            "DEPENDENCY_UNAVAILABLE",
            "One or more required dependencies are unavailable.",
            status_code=503,
            details={"dependencies": failures},
        )
    return HealthResponse()
