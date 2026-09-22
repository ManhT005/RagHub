import hashlib
import io
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import UploadFile

from app.core.config import Settings
from app.core.exceptions import AppError
from app.modules.documents.service import DocumentService


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> DocumentService:
    monkeypatch.setattr("app.modules.documents.service.MinioObjectStorage", lambda _: Mock())
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    instance = DocumentService(session, Settings(max_upload_size_mb=1))  # type: ignore[arg-type]
    instance.repository.workspace_exists = AsyncMock(return_value=True)  # type: ignore[method-assign]
    return instance


def upload(name: str, mime: str, data: bytes) -> UploadFile:
    return UploadFile(filename=name, file=io.BytesIO(data), headers={"content-type": mime})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,mime,data",
    [
        ("valid.pdf", "application/pdf", b"%PDF-test"),
        ("valid.txt", "text/plain", b"hello"),
        ("valid.md", "text/markdown", b"# Hello\nworld"),
    ],
)
async def test_upload_accepts_supported_files_and_safe_key(
    service: DocumentService,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    mime: str,
    data: bytes,
) -> None:
    organization_id, workspace_id = uuid.uuid4(), uuid.uuid4()
    document_id, version_id, job_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    document = SimpleNamespace(id=document_id)
    version = SimpleNamespace(id=version_id, status="QUEUED", created_at=datetime.now(UTC))
    job = SimpleNamespace(id=job_id)
    service.repository.create_upload = AsyncMock(return_value=(document, version, job))  # type: ignore[method-assign]
    from app.workers.tasks import ingest_document_version

    queued = Mock()
    monkeypatch.setattr(ingest_document_version, "delay", queued)
    response = await service.upload_document(
        organization_id=organization_id,
        workspace_id=workspace_id,
        upload=upload(f"../../{name}", mime, data),
    )
    key = service.storage.put.call_args.args[0]
    assert key.startswith(f"{organization_id}/{workspace_id}/")
    assert ".." not in key and name not in key
    assert (
        service.repository.create_upload.call_args.kwargs["checksum"]
        == hashlib.sha256(data).hexdigest()
    )
    assert service.repository.create_upload.call_args.kwargs["filename"] == name
    assert response.status == "QUEUED"
    queued.assert_called_once_with(str(version_id))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,mime,data,code",
    [
        ("bad.exe", "text/plain", b"a", "UNSUPPORTED_FILE_TYPE"),
        ("bad.pdf", "text/plain", b"%PDF-a", "INVALID_CONTENT_TYPE"),
        ("bad.pdf", "application/pdf", b"not a pdf", "INVALID_PDF"),
        ("empty.txt", "text/plain", b"", "EMPTY_FILE"),
    ],
)
async def test_upload_validation(
    service: DocumentService, name: str, mime: str, data: bytes, code: str
) -> None:
    with pytest.raises(AppError) as error:
        await service.upload_document(
            organization_id=uuid.uuid4(), workspace_id=uuid.uuid4(), upload=upload(name, mime, data)
        )
    assert error.value.code == code
    service.storage.put.assert_not_called()


@pytest.mark.asyncio
async def test_upload_size_limit(service: DocumentService) -> None:
    with pytest.raises(AppError) as error:
        await service.upload_document(
            organization_id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
            upload=upload("large.txt", "text/plain", b"x" * (1024 * 1024 + 1)),
        )
    assert error.value.code == "FILE_TOO_LARGE"


@pytest.mark.asyncio
async def test_upload_rejects_foreign_workspace(service: DocumentService) -> None:
    service.repository.workspace_exists = AsyncMock(return_value=False)  # type: ignore[method-assign]
    with pytest.raises(AppError) as error:
        await service.upload_document(
            organization_id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
            upload=upload("a.txt", "text/plain", b"hello"),
        )
    assert error.value.code == "WORKSPACE_NOT_FOUND"


@pytest.mark.asyncio
async def test_manual_retry_resets_same_job(
    service: DocumentService, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = SimpleNamespace(id=uuid.uuid4(), status="FAILED")
    version = SimpleNamespace(id=uuid.uuid4(), status="FAILED", created_at=datetime.now(UTC))
    job = SimpleNamespace(
        id=uuid.uuid4(),
        stage="FAILED",
        progress=85,
        attempts=4,
        error_code="INDEX_UNAVAILABLE",
        error_message="down",
        error_details={"x": 1},
    )
    service.repository.find_version_for_retry = AsyncMock(  # type: ignore[method-assign]
        return_value=(document, version, job)
    )
    from app.workers.tasks import ingest_document_version

    queued = Mock()
    monkeypatch.setattr(ingest_document_version, "delay", queued)
    response = await service.retry(uuid.uuid4(), uuid.uuid4(), version.id)
    assert response.job_id == job.id and response.document_version_id == version.id
    assert document.status == version.status == job.stage == "QUEUED"
    assert job.progress == job.attempts == 0
    assert job.error_code is job.error_message is job.error_details is None
    queued.assert_called_once_with(str(version.id))
