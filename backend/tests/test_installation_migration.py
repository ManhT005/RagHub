from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from alembic import command
from alembic.config import Config
from app.core.security import decode_token, hash_token
from tests.test_auth_refresh import service


@pytest.mark.integration
@pytest.mark.parametrize("existing", ["fresh", "user", "organization", "membership"])
async def test_full_migration_chain_preserves_existing_installation(isolated_engine, existing):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))

    def migrate(connection, revision):
        config.attributes["connection"] = connection
        command.upgrade(config, revision)

    async with isolated_engine.begin() as connection:
        await connection.run_sync(migrate, "20261004_0016")
        if existing in {"user", "membership"}:
            await connection.execute(
                text("""
                INSERT INTO users (id, email, status)
                VALUES ('00000000-0000-0000-0000-000000000001', 'existing@example.com', 'DISABLED')
            """)
            )
        if existing in {"organization", "membership"}:
            await connection.execute(
                text("""
                INSERT INTO organizations (id, name, slug, status)
                VALUES ('00000000-0000-0000-0000-000000000002', 'Existing', 'existing', 'ACTIVE')
            """)
            )
        if existing == "membership":
            await connection.execute(
                text("""
                INSERT INTO memberships (user_id, organization_id, role)
                VALUES ('00000000-0000-0000-0000-000000000001',
                        '00000000-0000-0000-0000-000000000002', 'ADMIN')
            """)
            )
        await connection.run_sync(migrate, "head")
        state = (
            (await connection.execute(text("SELECT * FROM installation_state"))).mappings().one()
        )
        assert state["id"] == 1 and state["installation_id"]
        assert state["status"] == ("UNINITIALIZED" if existing == "fresh" else "INITIALIZED")
        assert bool(state["initialized_at"]) == (existing != "fresh")
        if existing == "membership":
            assert str(state["owner_id"]) == "00000000-0000-0000-0000-000000000001"


@pytest.mark.integration
async def test_upgrade_preserves_refresh_sessions_with_nonzero_auth_version(isolated_engine):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))

    def migrate(connection, revision):
        config.attributes["connection"] = connection
        command.upgrade(config, revision)

    user_id, session_id = uuid4(), uuid4()
    async with isolated_engine.begin() as connection:
        await connection.run_sync(migrate, "20261004_0016")
        await connection.execute(
            text("""
            INSERT INTO users (id, email, status, auth_version)
            VALUES (:id, 'upgrade@example.com', 'ACTIVE', 4)
        """),
            {"id": user_id},
        )
        await connection.execute(
            text("""
            INSERT INTO user_sessions (id, user_id, refresh_token_hash, expires_at)
            VALUES (:id, :user_id, :token_hash, now() + interval '7 days')
        """),
            {"id": session_id, "user_id": user_id, "token_hash": hash_token("upgrade-refresh")},
        )
        await connection.run_sync(migrate, "head")
    sessions = async_sessionmaker(isolated_engine, expire_on_commit=False)
    async with sessions() as session:
        auth = service(session)
        result = await auth.refresh("upgrade-refresh")
        assert decode_token(result.access_token, auth.settings).auth_version == 4
