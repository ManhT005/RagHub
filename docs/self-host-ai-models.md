# Self-host AI configuration

Local Initial Setup creates Sentence Transformer and Ollama connections, registers
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384 dimensions) and
`gemma3:1b`, and saves organization defaults. Owner, organization, session and model
records commit together. A worker health job runs afterward; unavailable AI leaves
installation initialized. Retry model tests from AI Providers / Model Registry.
Setup does not download Ollama models. If `gemma3:1b` is absent, open the Ollama
provider, test its connection, and choose **Recommended → Cài đặt & đăng ký**.

Workspace creation preselects healthy defaults. Either model can be changed or left
for later. A chat-only or embedding-only workspace is `PARTIAL`; both healthy models
are `READY`. Model or connection health failures produce `WARNING`. Embedding
re-index progress is shown separately.

## Ollama models

The provider drawer contains Installed, Recommended and Manual sections. Installed
reads `/api/tags`; Recommended is a curated manifest with approximate download sizes,
not RAM/VRAM requirements. Downloads begin only after an explicit Install action.

`POST /api/v1/provider-connections/{id}/ollama/models/pull` returns `202` with a
persistent job. The Celery worker streams `/api/pull`, saves progress, verifies the
installed model, then registers it through the normal runtime health probe. Poll
`GET /api/v1/provider-connections/{id}/ollama/model-pulls/{job_id}` or reopen the
drawer. Only system admins in the connection's organization can operate these APIs.
One active download per connection is permitted. Failed jobs can be retried; stalled
jobs expire after two hours. Registration failure leaves the downloaded model in
Ollama, where it can be discovered and registered again.

Keep the existing `ollama-data` volume across restarts. Include model volumes when
using the existing backup command with `--include-models`. Never remove the volume
to retry a model download. Worker restarts redeliver unfinished jobs; Ollama reuses
downloaded layers. API restarts retain progress in PostgreSQL.

## NVIDIA NIM

Select NVIDIA NIM, supply an API key, and use
`https://integrate.api.nvidia.com/v1`. Chat uses the existing OpenAI-compatible adapter.
The host NVIDIA embedding request profile sends `input_type=query` for queries,
`input_type=passage` for documents, and `encoding_format=float`, including during
dimension inference. No engine changes are required.

## 9Router and trusted local endpoints

Local gateway access is disabled until exact hostnames are allowlisted in the API
and worker environment:

```env
TRUSTED_LOCAL_PROVIDER_HOSTS=host.docker.internal,9router
```

For a gateway running on the host, enter
`http://host.docker.internal:20128/v1`; the shared Compose configuration adds the
host-gateway mapping on Linux. For a gateway container on the RagHub network, use
`http://9router:20128/v1`. Supply its API key when enabled. Public provider catalog
entries retain public endpoint validation even when these local hosts are allowed.
Hostname suffix matches, arbitrary IP literals, metadata/link-local destinations,
credential-bearing URLs and HTTP redirects are rejected. Runtime/discovery requests
recheck endpoint policy. Allowlist only gateways you control.

OpenAI-compatible model discovery often has no capability metadata. Such rows remain
`UNKNOWN`; explicitly choose Chat or Embedding before registration.

Protocol references: [Ollama API](https://github.com/ollama/ollama/blob/main/docs/api.md),
[NVIDIA embedding API](https://docs.nvidia.com/nim/nemo-retriever/text-embedding/1.12.0/reference.html),
[9Router](https://github.com/decolua/9router).
