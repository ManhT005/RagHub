from pathlib import Path

import pytest
from sqlalchemy import text

from alembic import command
from alembic.config import Config


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
