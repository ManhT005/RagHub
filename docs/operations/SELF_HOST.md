# RagHub Self-host

The self-host API, public chat host and Celery worker consume the same engine:
`core_domain`, `application`, and `ports`. Configuration and concrete adapter wiring
belong to `composition/self_host.py`, `public_chat.py`, and `worker.py`.
The engine does not read environment variables or contain deployment/role checks.

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
docker compose --env-file .env.self-host -f infrastructure/docker-compose.self-host.yml exec api python -m app.cli bootstrap-owner --email owner@example.com
```

Bootstrap prompts for the password, creates an email-verified owner and default
internal organization in one transaction, and grants its ADMIN membership. Repeat
execution reports `unchanged` and preserves the password. It refuses to adopt an
unrelated existing identity or bootstrap a second owner into an occupied installation.
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
python scripts/self-host-smoke.py --env-file .env.selfhost-test --project raghub-selfhost-test --base-url http://localhost:18082 --owner-file .env.selfhost-owner.json --state-file .env.selfhost-state.json --compose-override infrastructure/docker-compose.self-host.build.yml --restart
```

This checks real Sentence Transformer (`all-MiniLM-L6-v2`, a smaller smoke model),
Ollama `gemma3:1b`, CLI bootstrap idempotency, password preservation, ingestion,
retrieval, Playground/public SSE, trusted citations, allowed/denied origins,
preflight and the served widget. It repeats retrieval/chat after a full runtime
restart. No external API key or production test seed is involved.

`self-host-smoke.yml` runs nightly, manually and for release-candidate tags. Regular
CI retains core-only, backend, adapter/integration, frontend, widget, Compose,
migration and image checks. A local verification report does not replace the full
CI result of a pull request into `develop`.

See [backup, restore and upgrade](SELF_HOST_OPERATIONS.md) before production use.
