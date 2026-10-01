# Phase-one database

The initial Alembic migration creates:

- `organizations` and `workspaces` for mandatory retrieval scope.
- `documents` for logical document metadata.
- `document_versions` for immutable storage/checksum state.
- `ingestion_jobs` for stage, progress and error reporting.

Public and tenant-owned IDs use UUIDs. `organization_id` and `workspace_id` are
stored directly on hot-path document/version records so repository and search
operations cannot accidentally omit scope.
