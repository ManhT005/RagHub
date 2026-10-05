"""Public ingestion errors and the policy for retrying the same stored file."""

RETRYABLE_ERROR_CODES = frozenset(
    {
        "STORAGE_UNAVAILABLE",
        "QUEUE_UNAVAILABLE",
        "EMBEDDING_UNAVAILABLE",
        "INDEX_UNAVAILABLE",
    }
)

ERROR_MESSAGES = {
    "STORAGE_UNAVAILABLE": "Document storage is temporarily unavailable. Try again later.",
    "QUEUE_UNAVAILABLE": "Ingestion could not be queued. Try again later.",
    "EMBEDDING_UNAVAILABLE": "Embedding is temporarily unavailable. Try again later.",
    "INDEX_UNAVAILABLE": "Search indexing is temporarily unavailable. Try again later.",
    "INVALID_PDF": "This PDF cannot be read. Upload a valid PDF.",
    "FAILED_UNSUPPORTED_OCR": "This PDF has no selectable text. OCR is not supported.",
    "TEXT_DECODE_FAILED": "Save the text file as UTF-8 and upload it again.",
    "EMPTY_FILE": "The uploaded file is empty.",
    "EMPTY_EXTRACTED_TEXT": "The document contains no extractable text.",
    "UNSUPPORTED_FILE_TYPE": "Upload a PDF, TXT or Markdown file.",
    "PARSE_FAILED": "The document could not be parsed.",
    "CHUNKING_FAILED": "The document could not be split into chunks.",
    "EMBEDDING_FAILED": "Embedding generation failed.",
    "INDEX_FAILED": "The document could not be indexed.",
}


def ingestion_error_message(code: str | None) -> str | None:
    if code is None:
        return None
    return ERROR_MESSAGES.get(code, "Document processing failed. Contact your administrator.")


class IngestionError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(message)
