# RagHub

RagHub is a multi-tenant chatbot platform built around retrieval-augmented
generation (RAG). This branch implements the phase-one foundation and a runnable
PDF ingestion vertical slice.

## What is included

- FastAPI API with typed settings, request IDs, health checks and a stable error envelope.
- Celery worker that parses PDF pages, creates stable chunks and indexes them in Elasticsearch.
- PostgreSQL metadata, an initial Alembic migration and MinIO object storage.
- Angular Admin shell with standalone routing and an NG-ZORRO layout.
- Docker Compose for the application and all local dependencies.

## Run locally with Docker

Copy `.env.example` to `.env`, replace the local-only secrets, then run:

```powershell
docker compose -f infrastructure/docker-compose.yml up --build -d
docker compose -f infrastructure/docker-compose.yml ps
```

Open the Admin shell at <http://localhost:8080>. API documentation is available
at <http://localhost:8080/api/v1/docs> and readiness at
<http://localhost:8080/health/ready>.

The vertical slice requires an organization and workspace row. Create the sample
scope and run the smoke test with:

```powershell
./scripts/bootstrap-sample-scope.ps1
./scripts/vertical-slice.ps1 -PdfPath ./sample.pdf -Query "search terms"
```

## Development

Backend commands are run from `backend`:

```powershell
python -m venv ../.venv
../.venv/Scripts/python -m pip install -r requirements.lock
../.venv/Scripts/python -m pytest
../.venv/Scripts/python -m ruff check .
```

Frontend commands are run from `apps/admin-web`:

```powershell
npm ci
npm start
npm test
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for branch and commit conventions and
[docs/architecture.md](docs/architecture.md) for the phase-one architecture.
