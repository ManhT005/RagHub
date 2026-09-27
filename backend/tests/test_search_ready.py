from types import SimpleNamespace
from uuid import UUID

import pytest

from app.modules.search.service import SearchService

ORGANIZATION_ID = UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000002")
DOCUMENT_ID = UUID("00000000-0000-0000-0000-000000000003")
VERSION_ID = UUID("00000000-0000-0000-0000-000000000004")


def hit(document_id: UUID = DOCUMENT_ID, version_id: UUID = VERSION_ID) -> dict[str, object]:
    return {
        "document_id": str(document_id),
        "document_version_id": str(version_id),
        "chunk_id": "00000000-0000-0000-0000-000000000005",
    }


class SessionStub:
    def __init__(self, rows: list[tuple[UUID, UUID]]) -> None:
        self.rows = rows
        self.statement = None

    async def execute(self, statement: object) -> list[tuple[UUID, UUID]]:
        self.statement = statement
        return self.rows


@pytest.mark.asyncio
async def test_retrieval_keeps_only_ready_document_version_pairs() -> None:
    other_document = UUID("00000000-0000-0000-0000-000000000006")
    session = SessionStub([(DOCUMENT_ID, VERSION_ID)])

    result = await SearchService(session)._ready_hits(  # type: ignore[arg-type]
        ORGANIZATION_ID,
        WORKSPACE_ID,
        [hit(), hit(other_document, VERSION_ID)],
    )

    assert result == [hit()]


@pytest.mark.asyncio
async def test_retrieval_ready_query_enforces_document_and_version_scope() -> None:
    session = SessionStub([])

    await SearchService(session)._ready_hits(  # type: ignore[arg-type]
        ORGANIZATION_ID, WORKSPACE_ID, [hit()]
    )

    sql = str(session.statement.compile(compile_kwargs={"literal_binds": True}))
    assert "documents.organization_id" in sql
    assert "documents.workspace_id" in sql
    assert "documents.status = 'READY'" in sql
    assert "documents.deleted_at IS NULL" in sql
    assert "document_versions.organization_id" in sql
    assert "document_versions.workspace_id" in sql
    assert "document_versions.status = 'READY'" in sql


@pytest.mark.asyncio
async def test_retrieval_with_no_candidates_skips_database() -> None:
    session = SimpleNamespace(execute=None)

    result = await SearchService(session)._ready_hits(  # type: ignore[arg-type]
        ORGANIZATION_ID, WORKSPACE_ID, []
    )

    assert result == []
