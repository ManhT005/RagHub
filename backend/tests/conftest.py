"""Database tests use disposable schemas, never application data."""

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.core.database import Base


@pytest.fixture
async def isolated_engine():
    url = os.getenv("RAGHUB_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set RAGHUB_TEST_DATABASE_URL to run PostgreSQL transaction tests.")
    schema = "test_" + uuid4().hex
    admin = create_async_engine(url, poolclass=NullPool)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        url, poolclass=NullPool, connect_args={"server_settings": {"search_path": schema}}
    )
    try:
        yield engine
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


@pytest.fixture
async def isolated_sessions(isolated_engine):
    async with isolated_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(isolated_engine, expire_on_commit=False)
