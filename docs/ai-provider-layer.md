# AI provider layer

RagHub stores AI provider configuration per organization. Workspaces bind one embedding
provider and one chat provider. Ingestion and query retrieval resolve the same active embedding
index snapshot, including provider, model, and dimension.

## Configuration

Set a dedicated encryption key before starting the API or worker:

```dotenv
PROVIDER_MASTER_KEY=a-long-random-value-kept-out-of-source-control
```

`APP_SECRET_KEY` remains reserved for application signing. Provider credentials are encrypted
with `PROVIDER_MASTER_KEY` before database storage and are represented as `has_secret` in API
responses. Put credentials in the API `secret` field. `config_json` rejects credential-like keys.

## Provider workflow

1. Create an embedding or chat provider with
   `POST /api/v1/organizations/{organization_id}/providers`.
2. Verify connectivity with `POST /api/v1/providers/{provider_id}/test`.
3. Bind providers with `PATCH /api/v1/workspaces/{workspace_id}/providers`.
4. Upload and query documents through the existing workspace endpoints.

When an embedding bind returns `reindex_job_id`, monitor it with
`GET /api/v1/workspaces/{workspace_id}/embedding-reindex-jobs/{job_id}`. The response includes
the current lifecycle status, document counters, timestamps, and a safe failure code/message.
Queue failures can be retried with `POST /api/v1/embedding-reindex-jobs/{job_id}/retry`.

OWNER and ADMIN roles may manage providers. Every provider lookup is scoped to the organization
from `X-Organization-ID`.

Changing an embedding model or dimension creates a BUILDING index version and a durable re-index
job. Search continues to use the old ACTIVE index. The worker re-embeds READY documents into the
new physical index, validates it, then changes the workspace active version in one database
transaction. A failure marks the new version FAILED and leaves the old version active.

## Provider types

- `OPENAI_COMPATIBLE`: embedding and streaming chat using `/embeddings` and
  `/chat/completions`.
- `GOOGLE_GEMINI`: embedding and streaming chat through Gemini's OpenAI-compatible endpoint.
- `LOCAL_TOKEN_HASH`: dependency-free deterministic embeddings for development and integration
  tests. These vectors are lexical features and are not suitable for production semantic search.
- `LOCAL_SENTENCE_TRANSFORMER`: local embedding. Install the `local-ai` optional dependency.
- `OLLAMA`: local streaming chat through `/api/chat`.

Start Ollama only for local deployments:

```bash
BACKEND_IMAGE_TARGET=local-ai \
  docker compose -f infrastructure/docker-compose.yml --profile local-ai up -d --wait
```

In PowerShell, set `$env:BACKEND_IMAGE_TARGET = "local-ai"` before the compose command. The
default `runtime` image does not install PyTorch or sentence-transformers. The `ollama-init`
service pulls `${OLLAMA_MODEL:-gemma3:1b}` into the shared Ollama volume on first startup. Create
the Ollama provider with the same model name. To select another model, set `OLLAMA_MODEL` before
starting the profile; Compose waits until the one-shot pull finishes.

Provider HTTP calls use bounded retries. Connection failures, 429, and upstream 502/503/504 may
retry before a chat token is emitted. Streaming is never restarted after the first token.
Provider errors map to stable 502 or 504 responses without including upstream bodies or secrets.
