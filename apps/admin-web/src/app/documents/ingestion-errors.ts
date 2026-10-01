const messages: Record<string, string> = {
  INVALID_PDF: "Không thể đọc PDF này. Hãy tải lên một tệp PDF hợp lệ.",
  FAILED_UNSUPPORTED_OCR:
    "PDF không có văn bản để chọn. Hệ thống chưa hỗ trợ OCR.",
  TEXT_DECODE_FAILED: "Hãy lưu tệp với mã hóa UTF-8 rồi tải lên lại.",
  EMPTY_FILE: "Tệp tải lên trống.",
  EMPTY_EXTRACTED_TEXT: "Không trích xuất được văn bản từ tài liệu.",
  UNSUPPORTED_FILE_TYPE: "Hãy tải lên tệp PDF, TXT hoặc Markdown.",
  INVALID_CONTENT_TYPE: "Loại nội dung không khớp với phần mở rộng của tệp.",
  FILE_TOO_LARGE: "Tệp vượt quá giới hạn dung lượng tải lên.",
  STORAGE_UNAVAILABLE:
    "Kho lưu trữ tài liệu tạm thời không khả dụng. Hãy thử lại sau.",
  QUEUE_UNAVAILABLE:
    "Không thể đưa tài liệu vào hàng đợi xử lý. Hãy thử lại sau.",
  EMBEDDING_UNAVAILABLE:
    "Dịch vụ tạo embedding tạm thời không khả dụng. Hãy thử lại sau.",
  INDEX_UNAVAILABLE:
    "Dịch vụ lập chỉ mục tạm thời không khả dụng. Hãy thử lại sau.",
  DOCUMENT_NOT_RETRYABLE: "Hãy sửa tài liệu và tải lên lại.",
  INVALID_DOCUMENT_STATUS: "Chỉ có thể thử lại tài liệu xử lý thất bại.",
  INGESTION_IN_PROGRESS:
    "Tài liệu vẫn đang được xử lý. Hãy tải lại trang và thử lại.",
  INSUFFICIENT_PERMISSION:
    "Vai trò của bạn trong tổ chức không có quyền thực hiện thao tác này.",
};

export function ingestionErrorMessage(code: string | null | undefined): string {
  return (
    (code && messages[code]) ||
    "Xử lý tài liệu thất bại. Hãy liên hệ quản trị viên."
  );
}
