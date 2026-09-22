"""Session advisory locks serialize ingestion across workers and stage commits."""

import hashlib
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection

logger = logging.getLogger(__name__)


def ingestion_lock_key(version_id: uuid.UUID) -> int:
    digest = hashlib.blake2b(version_id.bytes, digest_size=8, person=b"raghub-ingest").digest()
    return int.from_bytes(digest, byteorder="big", signed=True)


@asynccontextmanager
async def try_ingestion_lock(
    connection: AsyncConnection, version_id: uuid.UUID
) -> AsyncIterator[bool]:
    key = ingestion_lock_key(version_id)
    acquired = bool(await connection.scalar(select(func.pg_try_advisory_lock(key))))
    # Session locks survive commits. Keep this physical connection until the attempt ends.
    await connection.commit()
    try:
        yield acquired
    finally:
        if acquired and not connection.invalidated:
            try:
                await connection.rollback()
                await connection.execute(select(func.pg_advisory_unlock(key)))
                await connection.commit()
            except Exception:
                logger.exception("Could not release ingestion lock for %s", version_id)
                # Never return a connection with a session lock to a pool.
                await connection.invalidate()
