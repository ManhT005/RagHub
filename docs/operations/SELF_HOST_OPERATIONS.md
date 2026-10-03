# Backup, restore and upgrade

Use a maintenance window and restrict traffic at the upstream HTTPS proxy. Finish
long running ingestion/reindex jobs before backup. Never remove installation volumes
as part of an upgrade. The helper requires Docker and Python's standard library only.

## Consistent backup

```sh
python scripts/self-host-ops.py backup --env-file .env.self-host --project raghub-selfhost --directory /private/backups/2026-10-03
```

The destination must be empty. The helper stops writes through worker/API/gateway,
creates a PostgreSQL custom-format dump, stops MinIO/Elasticsearch/Redis, and archives
their named volumes. It captures the runtime environment and a SHA-256 manifest,
then restarts the previously running services and waits for health. It does not stop
or back up unrelated Docker projects.

The backup contains:

| Artifact | Purpose |
| --- | --- |
| `postgres.dump` | Users, memberships, provider configurations, documents/jobs, conversations, citations and usage |
| `minio-data.tar` | Uploaded source documents and object metadata |
| `elasticsearch-data.tar` | Exact indexes, preserved while Elasticsearch is stopped |
| `redis-data.tar` | AOF queue/admission state; expiring rate counters remain temporary |
| `runtime.env` | Installation secrets and configuration |
| `manifest.json` | Source project, image versions, volumes and integrity checks |

Add `--include-models` to capture Ollama models and Hugging Face cache, useful for an
offline restore. Otherwise download models again before the application smoke.
Store the whole directory in encrypted, access-restricted backup storage. The helper
sets private POSIX permissions; on Windows apply a private NTFS ACL. Backups under
the local `.backups/` directory are excluded from Git. Do not upload environment
files or backup archives as public CI artifacts.

`PROVIDER_MASTER_KEY` decrypts saved provider credentials; losing or replacing it
makes those credentials unusable. Preserve it and `APP_SECRET_KEY` independently
of the database backup. Database and MinIO passwords can be changed deliberately
during a restore provided the matching connection configuration is updated.

## Restore to a new installation

1. Copy `runtime.env` privately to `.env.restore`. Preserve `APP_SECRET_KEY` and
   `PROVIDER_MASTER_KEY`. Choose a new Compose project and, when the original host
   remains online, a different gateway port and proxy subnet/IP/trusted-proxy CIDR.
2. Use the same Elasticsearch image version as recorded in the manifest. The helper
   restores an offline data archive, which requires a matching Elasticsearch version;
   it is not an online cross-version snapshot. Upgrade after a successful restore.
3. Run:

```sh
python scripts/self-host-ops.py restore --env-file .env.restore --project raghub-restored --directory /private/backups/2026-10-03
```

The helper verifies archive checksums, critical secrets and the index image. It
refuses any existing target data volume and refuses the source project. It restores
objects/index/Redis first, initializes a fresh PostgreSQL service, runs `pg_restore`,
then starts migrations and runtime services. A failed restore can leave an incomplete
new project for diagnosis; it never replaces the source installation. Start again
with another fresh project after resolving the problem.

4. Verify readiness, owner login, source documents, provider tests, retrieval,
   Playground, embed config, origin policy and public chat before switching traffic.
   For a saved disposable smoke fixture:

```sh
python scripts/self-host-smoke.py --env-file .env.restore --project raghub-restored --base-url http://localhost:8080 --owner-file /private/smoke-owner.json --state-file /private/smoke-state.json --verify-only
```

Elasticsearch indexes can alternatively be rebuilt from MinIO source files and
database metadata through workspace reindex; retain provider model/dimension
snapshots. The automated helper restores the exact index archive so retrieval can be
verified immediately, without waiting for a rebuild.

## Upgrade

Read the release's migration/provider/model requirements and complete a backup first.
The helper captures the previous environment before switching its immutable image tag:

```sh
python scripts/self-host-ops.py upgrade --env-file .env.self-host --project raghub-selfhost --directory /private/backups/before-upgrade --image-tag sha-FULL_COMMIT_SHA
```

The sequence is backup → set new image tag → pull images → stop application writers
→ `alembic upgrade head` through the migration service → restart → readiness.
Verify application smoke before opening traffic. If pulling or migrating fails,
keep traffic closed and inspect logs; a failed migration is not automatically reversed.
For recovery restore the pre-upgrade backup to a new project using its saved image tag,
then switch traffic after smoke succeeds. Never downgrade Elasticsearch's data directory
or assume a database migration can be rolled back by starting an old API image.

## Release evidence

`self-host-smoke.yml` runs the real CPU local-AI lifecycle, restarts the stack,
backs it up, restores to a different project, and repeats retrieval/chat against the
restored database, objects and index. Local evidence is recorded in
[the verification report](SELF_HOST_VERIFICATION.md). Merge readiness still requires
the full CI checks on a pull request targeting `develop`.
