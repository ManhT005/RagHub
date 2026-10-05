# Self-host UI v1 implementation

Implemented on `feature/selfhost-ui-v1`, based on the existing
`refactor/core-package` checkout. The release scope is P0 in the local UI plans;
manual registration, connection editing and real status indicators are also
included because they support the v1 provider flow. Reference HTML/images are
local design inputs, excluded from Git. The authoritative contracts are in
[contracts.md](contracts.md).

## Screens and behavior

| Entry point | Delivered behavior |
| --- | --- |
| `/system/ai/providers` | Organization-scoped connections, supported/Coming soon catalog, three-step onboarding, masked credentials, test/discovery, manual registration fallback, edit and delete confirmation. |
| `/system/ai/models` | Registered model counts, capability/provider/status filters, test, enable/disable and delete confirmation; active/pending bindings are protected. |
| `/system/users` | Existing user/organization administration remains accessible to the active organization admin. |
| `/app/workspaces` | Aggregate summaries, search/filter/sort, create with a healthy embedding model, edit and confirmed deletion. Administrative scope is displayed without inventing an owner. |
| `/app/workspaces/:id/overview` | Real workspace/member/document/index summaries and authorized workspace editing. |
| `/app/workspaces/:id/documents` | Embedding summary above the table, status/type/name filters, PDF/TXT/MD upload, actual processing stages, retry/reindex, detail drawer, original download and confirmed deletion. |
| `/app/workspaces/:id/members` | Member candidates, assignment, explicit permission groups/dependencies, updates and removal; workspace grants do not change global roles. |
| `/app/workspaces/:id/ai` | Healthy model selection, chat binding, embedding impact preview, explicit migration confirmation and reindex progress/retry. |
| `/app/workspaces/:id/chat` | Existing authenticated streaming chat, real citations, chatbot selection/creation and authorized widget settings. |

Navigation and route/action gates follow the canonical eleven workspace
permissions. Backend endpoints enforce the same permissions, including direct
requests. Organization admins bypass workspace grants only inside their active
organization; disabled memberships never bypass access checks. Existing delegated
assignments receive full v1 permissions during migration.

Supported adapters are Gemini and OpenAI-compatible for chat/embedding,
Sentence Transformer for embedding, and Ollama for chat. Discovery uses each
provider's supported API. Unsupported factories appear as Coming soon; TokenHash
remains a legacy/development adapter and is absent from the new catalog.
Selectable registrations must be enabled, AVAILABLE and on an enabled CONNECTED
connection. Embedding dimension is checked against actual inference.

Provider secrets are encrypted on connections. Model/workspace responses contain
safe metadata, never ciphertext or credentials. Errors use sanitized codes and
localized UI messages. View-owned subscriptions end on destruction. Document
requests and chat streams are cancelled on workspace changes; stale document
responses cannot populate a different workspace.

## Index safety and metadata

Embedding changes reuse the existing active/pending index lifecycle. Preview
reports real affected ready documents/chunks. Existing retrieval continues on the
active index until the new index completes and activates atomically. Failed enqueue
or processing retains the old index and exposes retry. Concurrent migrations and
disabling/deleting bound registrations are rejected.

The host wraps the public index builder to persist chunk count, indexing time and
chunk strategy per document version/index. Pending builds do not overwrite active
metadata. Detail/list summaries read metadata for the active index; legacy rows
without persisted metadata display unknown values until reindexed. Counts come
from database aggregation rather than a frontend request for every workspace row.
The engine's behavior and public facade are unchanged. Its source now lives in
`raghub-core/src/raghub_core`, alongside the self-host backend, with standalone
packaging; see [the package refactor](../../architecture/RAGHUB_CORE_SIBLING_VERIFICATION.md).

## Database rollout and rollback

The pre-UI baseline is `20261003_0012`; the new head is `20261004_0015`:

| Revision | Change |
| --- | --- |
| `20261004_0013` | Workspace permission rows and legacy assignment backfill. |
| `20261004_0014` | Provider connections/model registration metadata; existing ProviderConfig IDs and workspace bindings remain stable, ciphertext moves to connections. |
| `20261004_0015` | Persisted document/version/index metadata. |

Before rollout, retain the old application images, deployment configuration and
encryption key, and take a database backup. Coordinate backups of PostgreSQL,
object storage and search indices if a full data restore may be needed. Quiesce
API writes and workers while migrating; finish or explicitly resolve pending
index work before rollback. Build/pull the release images, run the Compose
`migrate` service (`alembic upgrade head`), then start matching API, worker and web
images. Check gateway readiness and run the smoke suite before reopening writes.
The local source-build override is
`infrastructure/docker-compose.self-host.build.yml`.

Schema rollback uses the **new** migration image to execute
`alembic downgrade 20261003_0012` while API/worker writes are stopped, then restores
the matching old application images. The downgrade restores connection ciphertext
to each legacy model row and retains model IDs/bindings; v1 permission/status and
document metadata tables/columns are removed. Review any data created after the
upgrade before choosing downgrade. Keep the original encryption key. For a full
snapshot rollback, restore coordinated storage/database backups rather than
combining an old database with newer indices or files.

Upgrade, downgrade and repeat upgrade were verified on an isolated clone of the
existing database, including opaque ciphertext movement/restoration, legacy IDs,
bindings and eleven-grant backfill. The running source database was unchanged by
this verification. Its retained pre-UI dump can be supplied with `--snapshot` for
subsequent verification after the source has been upgraded.

## Deferred work

Bulk document operations, configurable advanced chunking, usage/cost dashboards,
benchmark recommendations, reranker/fallback chains and a versioned index rollback
UI remain later phases of the plans. Chunking currently uses the actual runtime
450-token / 80-overlap profile. Additional file formats and provider adapters need
runtime support before the UI can offer them.

Validation results and reproducible commands: [verification.md](verification.md).
