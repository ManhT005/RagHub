"""Upgrade both branches' schema histories in a disposable PostgreSQL schema."""

from pathlib import Path

import pytest
from sqlalchemy import text

from alembic import command
from alembic.config import Config

pytestmark = pytest.mark.integration
BACKEND = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("baseline", ["clean", "develop", "legacy_rag"])
async def test_migrations_reconcile_branch_histories(isolated_engine, tmp_path, baseline):
    config = Config(str(BACKEND / "alembic.ini"))
    if baseline != "clean":
        folder = tmp_path / baseline
        versions = folder / "versions"
        versions.mkdir(parents=True)
        (folder / "env.py").write_text(
            (BACKEND / "alembic" / "env.py").read_text(encoding="utf-8"), encoding="utf-8"
        )
        for path in (BACKEND / "alembic" / "versions").glob("*.py"):
            suffix = path.stem.split("_")[1]
            include = int(suffix) <= (22 if baseline == "develop" else 26)
            if baseline == "legacy_rag":
                include = include and suffix not in {"0021", "0022"}
                include = include or suffix in {"0027", "0028"}
            if not include:
                continue
            source = path.read_text(encoding="utf-8")
            if baseline == "legacy_rag":
                source = source.replace("20261006_0027", "20261005_0021")
                source = source.replace("20261006_0028", "20261005_0022")
                if suffix == "0027":
                    source = source.replace(
                        'down_revision = "20261005_0022"', 'down_revision = "20261005_0020"'
                    )
            (versions / path.name).write_text(source, encoding="utf-8")
        config.set_main_option("script_location", str(folder))
    else:
        config.set_main_option("script_location", str(BACKEND / "alembic"))

    def upgrade(connection, cfg):
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")

    async with isolated_engine.begin() as connection:
        await connection.run_sync(upgrade, config)
        if baseline != "clean":
            await connection.execute(
                text("INSERT INTO organizations (id, name, slug) VALUES (:id, 'Sentinel', :slug)"),
                {"id": "00000000-0000-0000-0000-000000000001", "slug": "preserved"},
            )
        config.set_main_option("script_location", str(BACKEND / "alembic"))
        await connection.run_sync(upgrade, config)
        head = await connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert head == "20261007_0033"
        assert (
            await connection.scalar(
                text(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_schema = current_schema() AND table_name = 'workspaces' "
                    "AND column_name = 'rerank_provider_id'"
                )
            )
            == 1
        )
        for table in ("provider_pools", "embedding_work_items", "local_ai_models"):
            assert await connection.scalar(text(f"SELECT to_regclass('{table}')")) is not None
        if baseline != "clean":
            assert (
                await connection.scalar(
                    text("SELECT count(*) FROM organizations WHERE slug = 'preserved'")
                )
                == 1
            )
