# Authentication and initial setup verification

Verified locally on 2026-10-05 on `feature/selfhost-auth-setup-hardening`.
All checks used disposable PostgreSQL schemas or separate Docker projects.

| Check | Result | Evidence |
| --- | --- | --- |
| Backend unit suite | PASS | 276 tests with `-m 'not integration'` |
| Selected PostgreSQL auth/setup suite | PASS | 24 tests, including refresh/setup races, rollback, CLI idempotency and upgrade compatibility |
| Frontend suite | PASS | 155 tests across 29 files |
| Core suite | PASS | 112 tests |
| Installed core isolation | PASS | 58 packaged modules imported with host, JWT and runtime dependencies blocked |
| Ruff | PASS | Backend, migrations, tests and added/changed smoke scripts |
| Compose | PASS | Local, GHCR, self-host, CPU/GPU and source-build models |
| Docker builds | PASS | Backend local-AI, admin web, widget, demo and gateway |
| Workflow validation | PASS | CI and self-host smoke checked with actionlint |
| Fresh browser setup | PASS | Desktop and 390px mobile layout, required services, Owner/organization creation and session handoff |
| Browser session lifecycle | PASS | Actual 1-minute expiry, exactly one refresh for concurrent UI 401s, reload/new-tab restore, transient `/auth/me` 503 and backend logout |
| LOCAL setup | PASS | Shared initialization service created multilingual MiniLM embedding and Ollama chat in an isolated schema; both real providers and setup refresh worked |
| Auth API lifecycle | PASS | Access expiry, refresh through API/nginx restart, cookie deletion, logout and password-change revocation |
| RAG and full restart | PASS | Real worker ingestion, retrieval, Playground/public SSE, citations, origins, widget and persistence across runtime restart |
| Existing-install migration | PASS | Fresh DB, existing user, organization and membership cases; active refresh with auth version 4 survived the full upgrade chain |
| Live upgrade | PASS | Cookie issued before session-version migration refreshed successfully after applying the new image/migration |
| Backup and restore | PASS | Database, storage, Elasticsearch, Redis and model cache restored into a different project; installation remained initialized and its saved refresh cookie, retrieval and chat worked |

The source smoke project used port 18085; the restore project used port 18086.
Secrets, refresh cookies, embed keys, backup archives and screenshots are under
the ignored `.backups/auth-setup-smoke` directory. Smoke state is sensitive and
must stay private. Production access TTL remains 15 minutes; only generated test
environments use one minute for expiry acceptance.

Regular CI now runs PostgreSQL auth/setup transaction tests before building images.
The scheduled/manual/RC-tag workflow runs fresh browser setup, API expiry and
LOCAL setup checks, real RAG, restart, backup and restore acceptance. Workflow
syntax was validated locally; remote GitHub Actions and RC-tag runs were not
triggered during this implementation.

See [Self-host operations and reproduction commands](SELF_HOST.md).
