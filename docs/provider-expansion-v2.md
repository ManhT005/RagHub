# Provider expansion v2

The control plane now separates catalog brands from runtime families. Groq,
OpenRouter, Cerebras and SiliconFlow use OpenAI-compatible transport; Voyage,
Cloudflare Workers AI and Hugging Face Inference have native adapters where needed.
Each connection owns an encrypted credential. Catalog identity is immutable.

| Catalog | Capabilities | Status | Discovery |
| --- | --- | --- | --- |
| Groq | Chat | Beta | Authenticated model list |
| OpenRouter | Chat | Beta | Key authentication, then live models and pricing metadata |
| Cerebras | Chat | Beta | Authenticated model list |
| SiliconFlow | Chat, embedding, rerank | Beta | Separate chat/embedding/reranker lists |
| Voyage | Embedding, rerank | Beta | Curated presets; connectivity uses a real embedding probe |
| Cloudflare Workers AI | Chat, embedding, rerank | Beta | Account-scoped native model search |
| Hugging Face Inference | Chat, embedding | Beta | Router chat models; live HF Inference feature-extraction mappings |
| GitHub Models | None | Retired | Disabled for new connections; existing records are preserved |

Free allocation/trial/mixed labels describe access policy. They do not promise
remaining quota or drive runtime routing. OpenRouter's free-model label comes from
upstream prompt/completion pricing; HF's embedding list excludes unserved and
staging repositories. Model registration always performs a runtime health probe.
The new brands use generic letter marks until reviewed official assets are added.

## Upgrade and credentials

Apply Alembic through `20261005_0022` to both API and worker deployments.
For existing Gemini installations that relied on a global environment key, run the
explicit migration in [provider-credentials.md](provider-credentials.md) before
switching to this runtime. Import never overwrites a manually rotated key.
`python -m app.cli bootstrap-owner` remains compatible.

Cloud writes through the old `/organizations/{id}/providers` and
`/providers/{id}` endpoints return `410 DEPRECATED_PROVIDER_API`. Use Provider
Connections and Model Registry. Legacy local APIs remain available. Reading,
testing and deleting old records remains available. Cloud catalog endpoints are
locked; custom endpoints belong to OpenAI-compatible connections. Runtime and
embedding snapshot endpoint checks happen before decrypted credentials are sent.

Cloudflare needs a 32-character Account ID and a connection-specific API token.
The endpoint is built from the account, not from a user-supplied URL. OpenRouter
allows only the App URL/App Name attribution fields; control characters in
headers are rejected. Secrets never belong in `config_json`.

Gemini embedding 2 uses native `embedContent`, one request per source chunk to
preserve vector cardinality. It uses text retrieval instructions rather than
`taskType`. Embedding 001 retains its native retrieval task types and output
dimension setting. Changing embedding model/dimension still creates a new index
version and follows the existing reindex/cutover flow; there is no embedding
fallback to another model.

## Optional reranking

Workspace > AI & Models can bind an available rerank model or turn reranking off.
`GET/PUT /workspaces/{id}/rerank-model` is scoped to the workspace's organization
and permissions. The settings bound candidates to 1–200, retained results to
1–100 (no greater than candidates), and wait time to 0.1–30 seconds. Defaults are
40 candidates, 8 retained results and 5 seconds. The caller's context limit also
caps the number returned.

Search and readiness filtering run first. Only those source chunks are sent to
the reranker. Returned indices/scores are validated; provider-returned text never
replaces original content or citations. Timeout, invalid response, authentication
or resolution failure uses the original ready search results. Logs/counters show
`DEGRADED_REQUEST`/`DEGRADED_RESOLUTION` without storing query text or credentials.
Set `AI_RERANK_ENABLED=false` to disable the stage globally. Changing a rerank
binding does not create an embedding reindex job.

## Local AI scaffold

System > Local AI lists three reviewed embedding repositories and downloads their
pinned revisions asynchronously. It shows queued/downloading/verifying/installed
or failed state, byte progress after each file, and retry after failure. Only
allowlisted tokenizer/config files and `model.safetensors` are downloaded; Python,
pickle and alternate model formats are excluded. The worker checks manifest size,
free disk space, file sizes and cache containment before atomic snapshot rename.
One download per organization is allowed at a time. Interrupted jobs become
retryable after 90 minutes. API and worker share the Hugging Face cache volume.

Downloads require the existing `local-ai` image/dependencies, a running Celery
worker and writable cache storage. `LOCAL_AI_DOWNLOAD_ENABLED=false` disables new
downloads. The compose cache directory is `/app/.cache/huggingface/local-ai`.
For a standalone process, set `LOCAL_AI_MODEL_DIR` to its persistent cache path.
`INSTALLED` means downloaded files, not runtime health or automatic workspace
activation. Loading, throughput tuning and integration with the local embedding
runtime remain with the other branch, as requested.

## Validation and rollout gate

Contract tests cover malformed vectors, indices/scores, count/dimension mismatch,
authentication, retries/Retry-After, stream interruption, endpoint identity,
credential rotation and multiple accounts. PostgreSQL tests cover bootstrap
idempotence and download persistence/isolation. Core retrieval tests cover
readiness/citation preservation and degraded rerank behavior. CI includes these
tests with a disposable database.

The local MiniLM download was exercised against the real pinned Hub revision:
91,567,913 bytes, ending in `INSTALLED`. Migrations 0021 and 0022 were tested up,
down and up on a disposable PostgreSQL database. Frontend build and regression
tests passed: backend 376 (6 infrastructure cases skipped), Core 126, frontend 166.
The local-ai Docker image builds successfully and imports the application and all
CLI entry points. No runtime tuning was performed on Sentence Transformer.

Before promoting a cloud brand from Beta, run live probes with a dedicated
connection credential for each advertised capability and retain sanitized results:

```sh
python -m app.cli.provider_smoke --organization-id <org> --connection-id <connection> \
  --model <served-model-id> --capability CHAT
python -m app.cli.provider_smoke --organization-id <org> --connection-id <connection> \
  --model <embedding-model-id> --capability EMBEDDING --dimension <dimension>
python -m app.cli.provider_smoke --organization-id <org> --connection-id <connection> \
  --model <rerank-model-id> --capability RERANK
```

Smoke uses only the named connection's encrypted credential, makes bounded
upstream requests, prints model/status/dimension or a sanitized error code, and
does not register models, bind workspaces or mutate data. Cloud runtime smoke
with real credentials is an operator gate; mock contract success does not promote
a brand automatically. Smart fallback chains and benchmarking remain later phases.

## Primary references checked on 2026-10-05

- [Groq OpenAI compatibility](https://console.groq.com/docs/openai)
- [OpenRouter key authentication](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-key)
- [OpenRouter model metadata](https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties)
- [Cerebras API](https://inference-docs.cerebras.ai/api-reference/chat-completions)
- [SiliconFlow model filters](https://docs.siliconflow.com/en/api-reference/models/get-model-list)
- [Voyage embeddings](https://docs.voyageai.com/docs/embeddings), [contextualized chunks](https://docs.voyageai.com/docs/contextualized-chunk-embeddings), [reranking](https://docs.voyageai.com/docs/reranker)
- [Cloudflare model search](https://developers.cloudflare.com/api/resources/ai/subresources/models/methods/list/), [reranker](https://developers.cloudflare.com/workers-ai/models/bge-reranker-base/)
- [HF provider mappings](https://huggingface.co/docs/inference-providers/hub-api), [feature extraction](https://huggingface.co/docs/inference-providers/tasks/feature-extraction)
- [Gemini embeddings](https://ai.google.dev/gemini-api/docs/embeddings), [deprecations](https://ai.google.dev/gemini-api/docs/deprecations)
- [GitHub Models retirement](https://github.blog/changelog/2026-07-01-github-models-is-being-fully-retired-on-july-30-2026/)
