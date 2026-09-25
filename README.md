# RagHub

RagHub is a multi-tenant retrieval-augmented generation (RAG) platform for building
chatbots over organization knowledge. It provides document ingestion, hybrid search,
streaming chat, tenant-aware access control, and configurable AI providers.

## Highlights

- FastAPI API with JWT authentication, organization membership, role-based access control,
  request IDs, health checks, and a stable error envelope.
- Asynchronous PDF, TXT, and Markdown ingestion through Celery, Redis, MinIO, and
  Elasticsearch.
- Hybrid BM25/vector retrieval with versioned embedding indexes and safe background
  re-indexing when embedding configuration changes.
- Organization-scoped embedding and chat providers, including OpenAI-compatible APIs,
  Google Gemini, Sentence Transformers, and Ollama.
- Encrypted provider credentials, bounded retries, provider health tests, and observable
  re-index jobs.
- Angular Admin application and a Docker Compose development environment.

## Stack

| Area | Technology |
|---|---|
| API and workers | Python 3.12, FastAPI, SQLAlchemy, Celery |
| Metadata and queue | PostgreSQL, Redis |
| Documents and retrieval | MinIO, Elasticsearch |
| Admin application | Angular, NG-ZORRO |
| Local AI | Sentence Transformers, Ollama |

## Run locally with Docker

Copy the example environment file and replace the development-only secrets:

```powershell
Copy-Item .env.example .env
docker compose -f infrastructure/docker-compose.yml up --build -d --wait
docker compose -f infrastructure/docker-compose.yml ps
```

The main local endpoints are:

- Admin: <http://localhost:8080>
- OpenAPI: <http://localhost:8080/api/v1/docs>
- Readiness: <http://localhost:8080/health/ready>

After registering, create an organization and workspace, then configure an embedding
provider and a chat provider through the provider API. Credentials belong in the `secret`
field and are encrypted with `PROVIDER_MASTER_KEY`; do not put them in `config_json`.

For a basic document smoke test, bootstrap a sample scope and run:

```powershell
./scripts/bootstrap-sample-scope.ps1
./scripts/vertical-slice.ps1 -PdfPath ./sample.pdf -Query "search terms"
```

## Run with local AI

The `local-ai` profile installs Sentence Transformers and starts Ollama. On first startup,
the one-shot initializer pulls `OLLAMA_MODEL` (`gemma3:1b` by default):

```powershell
$env:BACKEND_IMAGE_TARGET = "local-ai"
$env:OLLAMA_MODEL = "gemma3:1b"
docker compose -f infrastructure/docker-compose.yml --profile local-ai up --build -d --wait
```

Configure `LOCAL_SENTENCE_TRANSFORMER` with a Sentence Transformer embedding model, and
configure `OLLAMA` for chat with the `OLLAMA_MODEL` selected above. See
[AI provider setup](docs/ai-provider-layer.md) for the provider workflow, re-index lifecycle,
and supported options.

## Development

Run backend commands from `backend`:

```powershell
python -m venv ../.venv
../.venv/Scripts/python -m pip install -r requirements.lock
../.venv/Scripts/python -m pytest -p no:cacheprovider
../.venv/Scripts/python -m ruff check .
../.venv/Scripts/python -m alembic upgrade head
```

Run frontend commands from `apps/admin-web`:

```powershell
npm ci
npm start
npm test
```

## Documentation

- [API guide](docs/api.md)
- [AI provider layer](docs/ai-provider-layer.md)
- [Architecture](docs/architecture.md)
- [Database model](docs/database.md)
- [Ingestion QA](docs/ingestion-qa.md)
- [Contributing](CONTRIBUTING.md)
