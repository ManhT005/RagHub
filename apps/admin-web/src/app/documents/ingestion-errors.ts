const messages: Record<string, string> = {
  INVALID_PDF: 'This PDF cannot be read. Upload a valid PDF.',
  FAILED_UNSUPPORTED_OCR: 'This PDF has no selectable text. OCR is not supported.',
  TEXT_DECODE_FAILED: 'Save the file as UTF-8 and upload it again.',
  EMPTY_FILE: 'The uploaded file is empty.',
  EMPTY_EXTRACTED_TEXT: 'The document contains no extractable text.',
  UNSUPPORTED_FILE_TYPE: 'Upload a PDF, TXT or Markdown file.',
  INVALID_CONTENT_TYPE: 'The content type does not match the file extension.',
  FILE_TOO_LARGE: 'The file exceeds the upload size limit.',
  STORAGE_UNAVAILABLE: 'Document storage is temporarily unavailable. Try again later.',
  QUEUE_UNAVAILABLE: 'Ingestion could not be queued. Try again later.',
  EMBEDDING_UNAVAILABLE: 'Embedding is temporarily unavailable. Try again later.',
  INDEX_UNAVAILABLE: 'Search indexing is temporarily unavailable. Try again later.',
  DOCUMENT_NOT_RETRYABLE: 'Correct the document and upload it again.',
  INVALID_DOCUMENT_STATUS: 'Only failed documents can be retried.',
  INGESTION_IN_PROGRESS: 'Ingestion is still finishing. Refresh and try again.',
  INSUFFICIENT_PERMISSION: 'Your organization role cannot perform this action.',
};

export function ingestionErrorMessage(code: string | null | undefined): string {
  return (code && messages[code]) || 'Document processing failed. Contact your administrator.';
}
