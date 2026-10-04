"""Verify UI migrations against an isolated clone of the running self-host DB.

The source database is only read. Its dump is retained under the ignored .backups
directory. Upgrade/downgrade and credential assertions run exclusively in the clone.
"""

import argparse
import json
import re
import subprocess
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def run(command, *, content=None):
    result = subprocess.run(
        command, cwd=ROOT, input=content, capture_output=True, check=False
    )
    if result.returncode:
        raise RuntimeError(
            f"Migration verification command failed (exit {result.returncode})."
        )
    return result.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--database", default="raghub")
    parser.add_argument("--user", default="raghub")
    parser.add_argument("--output", type=Path, default=ROOT / ".backups/ui-validation")
    parser.add_argument("--snapshot", type=Path, help="Existing pre-UI pg_dump archive")
    args = parser.parse_args()
    clone = "raghub_ui_migration_" + uuid4().hex[:12]
    assert re.fullmatch(r"raghub_ui_migration_[0-9a-f]{12}", clone)
    postgres = ["docker", "exec", "-i", f"{args.project}-postgres-1"]

    def sql(statement, database=clone):
        return (
            run(
                [
                    *postgres,
                    "psql",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-U",
                    args.user,
                    "-d",
                    database,
                    "-A",
                    "-t",
                    "-c",
                    statement,
                ]
            )
            .decode("utf-8")
            .strip()
        )

    def rows(statement):
        output = sql(f"SELECT row_to_json(t) FROM ({statement}) t")
        return [json.loads(line) for line in output.splitlines() if line]

    def migrate(target, direction="upgrade"):
        code = (
            "import os; from sqlalchemy.engine import make_url; "
            "from alembic import command; from alembic.config import Config; "
            f'os.environ["DATABASE_URL"]=make_url(os.environ["DATABASE_URL"]).set(database={clone!r})'
            ".render_as_string(hide_password=False); "
            f'command.{direction}(Config("alembic.ini"), {target!r})'
        )
        run(
            [
                "docker",
                "compose",
                "--env-file",
                args.env_file,
                "-p",
                args.project,
                "-f",
                "infrastructure/docker-compose.self-host.yml",
                "-f",
                "infrastructure/docker-compose.self-host.build.yml",
                "--profile",
                "local-ai",
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "migrate",
                "python",
                "-c",
                code,
            ]
        )

    args.output.mkdir(parents=True, exist_ok=True)
    source_revision = sql("SELECT version_num FROM alembic_version", args.database)
    dump = (
        args.snapshot.read_bytes()
        if args.snapshot
        else run([*postgres, "pg_dump", "-U", args.user, "-d", args.database, "-Fc"])
    )
    run([*postgres, "createdb", "-U", args.user, clone])
    try:
        run(
            [*postgres, "pg_restore", "-U", args.user, "-d", clone, "--no-owner"],
            content=dump,
        )
        baseline = sql("SELECT version_num FROM alembic_version")
        assert baseline == "20261003_0012", (
            f"Expected pre-UI baseline, received {baseline}"
        )
        if not args.snapshot:
            (args.output / "before-ui-migrations.dump").write_bytes(dump)
        # An opaque fixture ciphertext proves movement/restoration even on a local-only DB.
        org_id = sql("SELECT id FROM organizations ORDER BY created_at LIMIT 1")
        fixture_id = str(uuid4())
        sql(f"""INSERT INTO provider_configs
            (id, organization_id, name, provider_type, capability, base_url, model, dimension,
             encrypted_secret, config_json, enabled)
            VALUES ('{fixture_id}', '{org_id}', 'Migration ciphertext fixture',
             'OPENAI_COMPATIBLE', 'EMBEDDING', 'https://provider.example/v1', 'fixture', 384,
             'opaque-migration-ciphertext', '{{}}', true)""")
        source = rows("SELECT id, encrypted_secret FROM provider_configs ORDER BY id")
        binding_query = (
            "SELECT id, embedding_provider_id, chat_provider_id, "
            "active_embedding_index_version_id, pending_embedding_index_version_id "
            "FROM workspaces ORDER BY id"
        )
        bindings = rows(binding_query)
        assignments = int(
            sql("""SELECT count(*) FROM workspace_memberships wm JOIN memberships m
            ON m.user_id = wm.user_id JOIN workspaces w ON w.id = wm.workspace_id
            WHERE m.organization_id = w.organization_id AND m.role = 'WORKSPACE_ADMIN'""")
        )
        migrate("head")
        assert sql("SELECT version_num FROM alembic_version") == "20261004_0016"
        assert (
            sql(
                f"SELECT c.catalog_id FROM provider_connections c JOIN provider_configs p ON p.connection_id=c.id WHERE p.id='{fixture_id}'"
            )
            == "compatible"
        )
        assert (
            sql(
                "SELECT count(*) FROM provider_connections WHERE provider_type IN ('GOOGLE_GEMINI', 'OLLAMA', 'LOCAL_SENTENCE_TRANSFORMER', 'OPENAI_COMPATIBLE') AND catalog_id IS NULL"
            )
            == "0"
        )
        moved = rows(
            "SELECT p.id, c.encrypted_secret FROM provider_configs p "
            "JOIN provider_connections c ON c.id=p.connection_id ORDER BY p.id"
        )
        assert moved == source, "Model IDs/ciphertext did not survive migration"
        assert (
            sql(
                "SELECT count(*) FROM provider_configs WHERE encrypted_secret IS NOT NULL"
            )
            == "0"
        )
        assert rows(binding_query) == bindings, (
            "Workspace binding changed during migration"
        )
        assert (
            int(sql("SELECT count(*) FROM workspace_membership_permissions"))
            == assignments * 11
        )
        print(
            f"PASS: upgrade preserves {len(source)} model IDs, credentials, bindings and grants",
            flush=True,
        )
        migrate(baseline, "downgrade")
        assert (
            rows("SELECT id, encrypted_secret FROM provider_configs ORDER BY id")
            == source
        )
        assert rows(binding_query) == bindings
        print("PASS: downgrade restores legacy credentials and bindings", flush=True)
        migrate("head")
        assert rows(binding_query) == bindings
        print(
            "PASS: repeat upgrade; source database remains at its original revision",
            flush=True,
        )
        assert (
            sql("SELECT version_num FROM alembic_version", args.database)
            == source_revision
        )
    finally:
        # This name is generated above and never equals the source database.
        run([*postgres, "dropdb", "-U", args.user, clone])


if __name__ == "__main__":
    main()
