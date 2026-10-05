# RagHub Self-host

The self-host API, public chat host and Celery worker consume the standalone
`raghub-core` package from `raghub-core/src/raghub_core`. The `backend` project is
the self-host host and its infrastructure adapters; composition consumes public
use cases through `raghub_core.api`, while adapters implement `raghub_core.ports`.
Configuration and concrete adapter wiring
belong to `composition/self_host.py`, `public_chat.py`, and `worker.py`.
The engine does not read environment variables or contain deployment/role checks.

Source builds use the repository root as Docker context and `backend/Dockerfile`
so the image can install the sibling core package. The existing image names,
Compose service names, bootstrap, migrations and backup/restore commands remain
the same. Development Compose mounts `backend/app` and `raghub-core/src/raghub_core`;
the self-host build override installs core into the production image without source
mounts. See the [backend development guide](../../backend/README.md) and
[package verification](../architecture/RAGHUB_CORE_SIBLING_VERIFICATION.md).

## Installation from images

Requirements: Docker Engine with Compose v2, an x86-64 CPU, Internet access for the
first model download, and an HTTPS reverse proxy for browser access. Start with
8 GB RAM for the small local models used by the smoke test; production requirements
depend on the model, document sizes and concurrent chats. NVIDIA is optional.

1. Copy `.env.self-host.example` to `.env.self-host`.
2. Set an immutable published `RAGHUB_IMAGE_TAG`. Fill `APP_SECRET_KEY`,
   `PROVIDER_MASTER_KEY`, `POSTGRES_PASSWORD`, and `S3_SECRET_KEY` with distinct
   random values. Use at least 32 random characters for the application keys.
   For example, generate each value with `python -c "import secrets; print(secrets.token_urlsafe(36))"`.
3. Set `FRONTEND_URL` to your HTTPS URL. Use URL-safe database passwords or provide
   a `DATABASE_URL` containing a URL-encoded password. Keep the environment file private.
4. Run:

```sh
docker compose --env-file .env.self-host -f infrastructure/docker-compose.self-host.yml --profile local-ai pull
docker compose --env-file .env.self-host -f infrastructure/docker-compose.self-host.yml --profile local-ai up -d --wait api worker nginx ollama
docker compose --env-file .env.self-host -f infrastructure/docker-compose.self-host.yml --profile local-ai run --rm ollama-init
```

Open `/setup` through your HTTPS gateway. The wizard checks API, PostgreSQL,
Redis, Elasticsearch and MinIO, then creates an email-verified Owner, organization
and ADMIN membership in one transaction. Use a password of 12–128 characters.
Local AI seeds Sentence Transformer (multilingual MiniLM, 384 dimensions) and
Ollama `gemma3:1b`; connectivity checks run after creation and do not block Owner
setup when models are not ready. Select these models in a workspace's AI & Models.
External Gemini/OpenAI-compatible configuration can be opened after setup or
skipped. SMTP and AI are optional; infrastructure secrets stay in the environment.

Keep the initial gateway accessible only to the installing administrator until
setup completes. Once initialized, `/setup/initialize` returns
`409 INSTALLATION_ALREADY_INITIALIZED`; `/setup` redirects to login or workspaces.
Migration `20261005_0017` marks any database with existing users/organizations
initialized, including disabled owners. It never reopens setup based on user count.

CLI remains available for headless installations:

```sh
docker compose --env-file .env.self-host -f infrastructure/docker-compose.self-host.yml exec api python -m app.cli bootstrap-owner --email owner@example.com
```

CLI and web use the same initialization service and singleton transaction lock.
Repeating CLI for the same active installation Owner reports `unchanged` and
preserves the password. It refuses unrelated identities and second Owners, even
when a different organization slug is supplied.
Automation can use `bootstrap-owner --stdin-json` with an input JSON containing
`email` and `password`; keep passwords out of command arguments and logs.

Open the Console, create a workspace, then open workspace Settings and select
**Dùng local Ollama**. This creates/binds Sentence Transformer embedding (384
dimensions, multilingual MiniLM) and Ollama chat. Upload a document, wait for READY,
configure/publish a chatbot, test it in Playground and set the exact allowed website
origins in Integration. Copy the resulting embed script to that website.
The AI Settings page manages provider configurations and their separate connectivity
checks. Gemini and OpenAI-compatible providers remain optional.

Only the gateway publishes a port. Database, Redis, Elasticsearch, MinIO and Ollama
remain inside Docker networks. Persistent named volumes store database, index,
objects, Redis AOF, Ollama models and the Hugging Face model cache. `down` preserves
these volumes; `down -v` deletes them and is for disposable tests only.

For NVIDIA hosts add `-f infrastructure/docker-compose.gpu.yml` to the Compose
commands. CPU installations use no GPU device reservation. Use the `local-ai` image
suffix for Sentence Transformer; an empty suffix selects the smaller external-AI image.

SMTP is optional for `APP_ENV=selfhost`. Password login and bootstrap work without
it; email registration/recovery return EMAIL_NOT_CONFIGURED, and tokens are never
logged. If you enable SMTP, supply the complete configuration. HTTPS is required for
the secure refresh cookie outside development/test environments.

## Health and persistence

Access tokens default to 15 minutes (`ACCESS_TOKEN_TTL_MINUTES`), and HttpOnly
refresh cookies default to 7 days (`REFRESH_TOKEN_TTL_DAYS`). Keep HTTPS enabled:
the refresh cookie is Secure in self-host mode. The Console rotates refresh tokens,
shares concurrent refresh requests, restores cookie sessions in new tabs, and
keeps local state during gateway/network failures. Logout revokes the refresh
session and clears its cookie; password changes/reset revoke previous sessions.
Refresh sessions also carry the issuing user's `auth_version`, so a stale policy
version cannot mint a new access token. Migration `20261005_0018` backfills existing
sessions from their users to preserve valid login sessions during upgrade.

`/health/live` checks that the process responds. `/health/ready` checks PostgreSQL,
Redis, Elasticsearch and MinIO. AI connectivity is checked independently through
provider tests; a stopped Ollama service does not fail basic API readiness.

The default organization is an ownership/isolation boundary rather than a customer
control plane. Workspaces are the primary Console workflow. User management is
under `/system/users`, with `/app/users` redirecting there. Existing `/admin/users`
API clients remain supported.

Disabling a user here disables only their membership in the current organization.
Their global identity, sessions and access to other organizations remain intact.
Globally suspended identities cannot be reactivated by an organization administrator.
Migration `20261003_0012` preserves existing global suspensions and marks their
memberships disabled; it does not silently reactivate accounts.

## Repeatable release smoke

For source verification on a disposable machine:

```sh
python scripts/self-host-test-env.py
docker compose --env-file .env.selfhost-test -p raghub-selfhost-test -f infrastructure/docker-compose.self-host.yml -f infrastructure/docker-compose.self-host.build.yml --profile local-ai build api admin-web chat-widget widget-demo nginx
docker compose --env-file .env.selfhost-test -p raghub-selfhost-test -f infrastructure/docker-compose.self-host.yml -f infrastructure/docker-compose.self-host.build.yml --profile local-ai up -d --wait api worker nginx ollama
python scripts/self-host-smoke.py --env-file .env.selfhost-test --project raghub-selfhost-test --base-url http://localhost:18082 --owner-file .env.selfhost-owner.json --state-file .env.selfhost-state.json --compose-override infrastructure/docker-compose.self-host.build.yml --restart --auth-expiry-seconds 65
```

This checks real Sentence Transformer (`all-MiniLM-L6-v2`, a smaller smoke model),
Ollama `gemma3:1b`, fresh Setup API initialization, immediate session handoff,
closed setup after initialization, actual access expiry, refresh rotation through
API/gateway restarts, logout cookie deletion, password-change revocation,
CLI idempotency, password preservation, ingestion,
retrieval, Playground/public SSE, trusted citations, allowed/denied origins,
preflight and the served widget. It repeats retrieval/chat after a full runtime
restart. No external API key or production test seed is involved.

Generated test environments use a 1-minute access TTL so expiry can be verified;
production defaults remain 15 minutes. The Python client explicitly sends Secure
cookies only on loopback HTTP smoke; production browser traffic requires HTTPS.
For real browser acceptance, install `playwright==1.56.0` and Chromium, then run:

```sh
python scripts/self-host-auth-browser.py --base-url http://localhost:18082 --owner-file .env.selfhost-owner.json --auth-expiry-seconds 65
```

To exercise the fresh wizard itself, run browser acceptance with `--initialize`
before API smoke, then pass `--existing-setup` to API smoke. The browser checks
desktop/mobile setup, exactly one refresh for concurrent expired-token requests,
reload/new-tab cookie restoration, preservation of session on `/auth/me` 503,
closed setup routing, and backend logout. Screenshots stay in `.backups`.

API smoke also runs `self-host-local-setup-smoke.py` inside the API container.
It initializes a LOCAL installation in a temporary PostgreSQL schema, checks real
multilingual embedding/Ollama connectivity and the setup refresh session, then
drops only that schema. The main installation and its users remain intact.
Smoke state files contain a refresh cookie as well as the embed key; keep them
private. Restore verification rotates that persisted refresh session before login.

Backup captures the entire PostgreSQL database, including `installation_state`
and refresh sessions. Preserve `APP_SECRET_KEY` and `PROVIDER_MASTER_KEY` on restore.
The restore smoke asserts initialized status before checking RAG; restored data
must never open a fresh setup portal.

`self-host-smoke.yml` runs nightly, manually and for release-candidate tags. Regular
CI retains core-only, backend, adapter/integration, frontend, widget, Compose,
migration and image checks. A local verification report does not replace the full
CI result of a pull request into `develop`.

See [backup, restore and upgrade](SELF_HOST_OPERATIONS.md) before production use.
