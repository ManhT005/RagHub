from uuid import UUID

from fastapi import UploadFile

from app.core.exceptions import AppError
from raghub_core.domain.documents.upload import UploadDocumentCommand, validate_upload_metadata


async def read_upload(upload: UploadFile, *, max_size_mb: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while chunk := await upload.read(1024 * 1024):
        total += len(chunk)
        if total > max_size_mb * 1024 * 1024:
            raise AppError(
                "FILE_TOO_LARGE", f"The upload exceeds {max_size_mb} MB.", status_code=413
            )
        chunks.append(chunk)
    if total == 0:
        raise AppError("EMPTY_FILE", "The uploaded file is empty.")
    return b"".join(chunks)


async def upload_from_http(service, organization_id: UUID, workspace_id: UUID, upload: UploadFile):
    # Preserve validation order and bound memory before constructing the bytes command.
    if not await service.repository.workspace_exists(organization_id, workspace_id):
        raise AppError(
            "WORKSPACE_NOT_FOUND",
            "Workspace was not found in the current organization.",
            status_code=404,
        )
    filename, _, mime = validate_upload_metadata(upload.filename or "", upload.content_type or "")
    content = await read_upload(upload, max_size_mb=service.settings.max_upload_size_mb)
    return await service.upload(
        UploadDocumentCommand(
            organization_id,
            workspace_id,
            filename,
            mime,
            content,
        )
    )
