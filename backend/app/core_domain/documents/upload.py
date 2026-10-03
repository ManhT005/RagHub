from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from uuid import UUID

from app.core_domain.errors import AppError

SUPPORTED_TYPES = {
    ".pdf": {"application/pdf", "application/x-pdf"},
    ".txt": {"text/plain"},
    ".md": {"text/markdown", "text/plain"},
}


@dataclass(frozen=True)
class UploadDocumentCommand:
    organization_id: UUID
    workspace_id: UUID
    filename: str
    content_type: str
    content: bytes


@dataclass(frozen=True)
class UploadReceipt:
    document_id: UUID
    document_version_id: UUID
    job_id: UUID
    status: str
    created_at: datetime


@dataclass(frozen=True)
class RetryDocumentState:
    receipt: UploadReceipt
    error_code: str | None


def validate_upload_metadata(filename: str, content_type: str) -> tuple[str, str, str]:
    filename = PurePosixPath(filename.replace("\\", "/")).name
    extension = PurePosixPath(filename).suffix.lower()
    if not filename or extension not in SUPPORTED_TYPES:
        raise AppError("UNSUPPORTED_FILE_TYPE", "Only PDF, TXT and Markdown files are supported.")
    mime = content_type.split(";", 1)[0].strip().lower()
    if mime not in SUPPORTED_TYPES[extension]:
        raise AppError(
            "INVALID_CONTENT_TYPE", "The content type does not match the file extension."
        )
    return filename, extension, mime


def validate_upload_content(content: bytes, extension: str, max_size_mb: int) -> None:
    if len(content) > max_size_mb * 1024 * 1024:
        raise AppError("FILE_TOO_LARGE", f"The upload exceeds {max_size_mb} MB.", status_code=413)
    if not content:
        raise AppError("EMPTY_FILE", "The uploaded file is empty.")
    if extension == ".pdf" and not content.startswith(b"%PDF-"):
        raise AppError("INVALID_PDF", "The uploaded file is not a valid PDF.")
