# Self-host UI v1 contracts

The UI runs in the Angular/NG-ZORRO host. `raghub_core.api` and Core behavior stay
unchanged. Provider connections own encrypted credentials; model registrations
retain existing provider-config IDs and workspace/index foreign keys. Legacy
provider endpoints and workspace-console bookmarks remain compatible.

## Workspace permissions

`workspace.view`, `workspace.edit`, `document.view`, `document.upload`,
`document.reindex`, `document.delete`, `chat.use`, `ai.view`,
`ai.change_embedding`, `member.view`, `member.manage`.

An active organization ADMIN bypasses permission rows within that organization.
Delegated users require an active organization membership, workspace assignment
and the requested permission. Mutations imply their corresponding view permission;
every workspace grant includes `workspace.view`. Existing delegated assignments
receive all v1 permissions during migration. Permissions never grant system-level
provider/credential administration.

## Resources and delivery

- `/ai/provider-catalog`: backend-supported metadata, without credentials.
- `/organizations/{id}/provider-connections`: connection CRUD; connection test
  and model discovery live under `/provider-connections/{id}`.
- `/organizations/{id}/models`: registered models, filtered by capability,
  availability and provider type. Runtime registration IDs remain stable.
- `/workspaces`: aggregate summaries, without per-row frontend API requests.
- `/workspaces/{id}/me/permissions` and `/members`: workspace access management.
- `/workspaces/{id}/documents`: persisted metadata, authorized detail/download.
- `/workspaces/{id}/embedding-model/preview`: read-only impact calculation;
  confirmation uses the existing binding/pending-index/reindex workflow.

Connection states: `UNTESTED`, `CONNECTED`, `DEGRADED`, `ERROR`.
Model availability: `UNTESTED`, `AVAILABLE`, `UNAVAILABLE`, `DISABLED`.
Pickers require AVAILABLE models on enabled CONNECTED connections.
Document stages preserve UPLOADED, QUEUED, PARSING, CHUNKING, EMBEDDING,
INDEXING, READY and FAILED; no synthetic processing states replace them.

## UI routes and behavior

System: `/system/ai/providers`, `/system/ai/models`, `/system/users`.
Workspace: `/app/workspaces/:id/{overview,documents,chat,members,ai}`.
Navigation hides unavailable permissions; discoverable actions may be disabled
with an explanation. Backend checks remain authoritative. No fake owners,
benchmarks, advanced chunking options or unsupported provider factories appear.
The visual direction uses neutral light surfaces, indigo primary actions, a
4/8px spacing rhythm, accessible focus, responsive tables and modal/drawer flows.

Polling runs only while document/reindex work remains nonterminal and ends when
the view is destroyed. Failed embedding migration retains the old active index.
Typed API errors map to safe localized messages; provider raw responses and
credentials must never be rendered or logged.
