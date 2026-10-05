# Core isolation and self-host verification

This report records the original extraction and operations checks. Core now lives
in the sibling `raghub-core` project, with a separate test suite and wheel; see
[current package verification](../architecture/RAGHUB_CORE_SIBLING_VERIFICATION.md).
The totals below remain historical and include core tests in the original backend suite.

Verified locally on **2026-10-04** on branch `refactor/core-isolation-selfhost`,
starting from the user-provided plan commit `147eb5d`. The implementation plan
itself is unchanged. Development and verification use separate Docker projects;
the existing user installation and `develop` are untouched.

## Implemented scope

| Plan stages | Result |
| --- | --- |
| A, I, J | Typed retrieval/context/citations, async storage, transport-free errors, service boundary gate and a complete fake-port upload-to-chat flow |
| B, D, E | Separate self-host, public-chat and worker composition; Redis admission outside business modules; shared RAG/indexing use cases |
| C, F, G | Atomic owner/default-organization bootstrap, grouped host configuration, required secrets, gateway-only exposure, CPU local AI and optional GPU override |
| H, K, L | Health, real local AI smoke, restart persistence, consistent backup, fresh-project restore, upgrade helper/docs and nightly/manual/RC smoke workflow |
| M | Console shell, workspace sections, AI Settings, System/Users, route-aware workspace navigation and membership-scoped suspension |

Compatibility facades, existing API paths and role names remain in the control
plane. Optional future host/admission abstractions and bulk folder/role renaming
are unnecessary for the enforced engine boundary and are not part of this change.

## Automated local checks

| Check | Evidence |
| --- | --- |
| Minimal-dependency core suite | **58 passed**; includes architecture gates and full fake-port upload, ingestion, retrieval and streaming chat |
| Full backend suite with live infrastructure | **303 passed**, including 15 integration tests against PostgreSQL, Redis, Elasticsearch, MinIO, API and gateway |
| Operations failure-path tests added afterward | **2 passed**; incomplete integrity manifests fail before Docker; a failed service stop still resumes previously running services |
| Backend lint | Ruff passed |
| Frontend | **59 passed** across 14 test files; production build passed |
| Widget | **4 passed**; TypeScript compilation passed |
| Compose | Local/runtime/local-AI, registry/runtime/local-AI, CPU self-host, GPU override and mandatory secrets validated |
| Workflows | actionlint 1.7.7 passed |
| Database | Single Alembic head `20261003_0012`; fresh migration and existing self-host upgrade passed; `alembic check` detected no pending model changes |
| CPU images | Backend local-AI and Console images built; real AI verification passed after the final membership migration |

Core tests run without runtime dependencies using `requirements-core-test.lock`.
Their results are also included in the backend total; they are not extra backend
tests. The operations tests execute without Docker or installation secrets.

Live integration coverage includes concurrent Redis admission, lease expiry and
cleanup, organization/workspace scope, ingestion retries, PostgreSQL locking,
conversation persistence and workspace reindex with a changed embedding dimension.
The membership regression logs into two organizations, disables access at A,
proves the same token and subsequent login still work at B, then restores access
at A. Owner bootstrap tests prove idempotency, password preservation and atomic
refusal to adopt an unrelated identity.

## Actual CPU local-AI lifecycle

Project `raghub-selfhost-test` used the self-host Compose package and locally built
images with the source-verification override. It started with fresh persistent
volumes and private, generated installation secrets. Production test-account seeds
and manual database inserts were not used.

The smoke downloaded **Sentence Transformer `all-MiniLM-L6-v2`** (384 dimensions)
and **Ollama `gemma3:1b`**, then verified:

1. CLI owner bootstrap, repeat bootstrap without password replacement and login.
2. Workspace creation, real embedding/chat provider connectivity and binding.
3. TXT upload through the API and asynchronous ingestion to READY.
4. Retrieval and Playground SSE with a document-specific answer and trusted citations.
5. Publication, embed configuration, allowed/forbidden origins and CORS preflight.
6. Public SSE through the gateway, served widget script and Console shell.
7. Restart of PostgreSQL, Redis, Elasticsearch, MinIO, Ollama, API, worker and gateway,
   followed by successful retrieval and both chat entry points on existing data.

After the final image rebuild and migration `20261003_0012`, owner login,
retrieval, Playground/public SSE, citations, origin policy and widget checks passed
again. These runs used CPU only and required no external API key.

The Console's default embedding model is multilingual MiniLM. The smoke uses the
smaller English MiniLM model to reduce download/runtime cost while exercising the
same actual adapter; it does not claim to test that default model's multilingual
answer quality.

## Actual backup and restore

`self-host-ops.py backup --include-models` quiesced the disposable installation,
captured its PostgreSQL dump, offline MinIO/Elasticsearch/Redis archives, runtime
secrets, Ollama models and Hugging Face cache, and resumed healthy services.
Checksums and the manifest were written under the ignored private `.backups/`
directory. No credentials or backup archives were committed.

The source installation was stopped to free CPU/RAM. A different project,
`raghub-selfhost-restore`, used a different gateway port and network and fresh data
volumes. The helper verified the backup, restored the database/objects/index/cache
and started healthy services. `self-host-smoke.py --verify-only` then passed owner
login, retrieval, Playground/public SSE, citations, origin policy and widget checks
against the restored installation.

The existing source database was subsequently upgraded to the membership migration
on the final image and passed the same application checks. The registry pull/tag
switch upgrade path is implemented and documented; it has not been exercised
against a newly published remote release in this local run.

## Remaining release verification

These results cover local source-built images and disposable Compose installations.
They do not claim a clean-machine pull from a newly published GHCR release,
hardware GPU execution, external Gemini/OpenAI calls, browser end-to-end automation,
or the remote GitHub Actions outcome. GPU configuration is validated structurally.

Frontend build retains the existing initial-bundle budget warning (1.73 MB versus
1.25 MB). Alembic retains the existing cyclic-foreign-key sorting warning between
workspaces and embedding index versions; schema comparison still passes.

The full PR checks targeting `develop` must be green before merge. The new
self-host smoke workflow can run manually, nightly and for release-candidate tags.
Use [installation instructions](SELF_HOST.md) and
[backup/restore/upgrade procedures](SELF_HOST_OPERATIONS.md) for release validation.
