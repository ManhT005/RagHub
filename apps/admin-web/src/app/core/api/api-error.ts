const MESSAGES: Record<string, string> = {
  PROVIDER_AUTH_FAILED: "Không thể xác thực provider. Kiểm tra API key.",
  PROVIDER_UNREACHABLE:
    "Không thể kết nối provider. Kiểm tra endpoint và dịch vụ.",
  PROVIDER_DISABLED: "Provider đang tắt.",
  MODEL_DISCOVERY_UNSUPPORTED:
    "Provider chưa hỗ trợ tìm model. Nhập Model ID thủ công.",
  MODEL_NOT_AVAILABLE:
    "Model chưa sẵn sàng. Kiểm tra kết nối và model trước khi chọn.",
  MODEL_DIMENSION_MISMATCH:
    "Dimension thực tế không khớp với model đã đăng ký.",
  WORKSPACE_ACCESS_DENIED: "Bạn không có quyền truy cập workspace này.",
  WORKSPACE_PERMISSION_DENIED: "Bạn không có quyền thực hiện thao tác này.",
  DOCUMENT_TOO_LARGE: "Tệp vượt quá giới hạn 25 MB.",
  FILE_TOO_LARGE: "Tệp vượt quá giới hạn 25 MB.",
  EMPTY_FILE: "Tệp tải lên không được để trống.",
  INVALID_CONTENT_TYPE: "Loại nội dung không khớp với phần mở rộng của tệp.",
  REINDEX_IN_PROGRESS:
    "Workspace đang reindex. Chờ tác vụ hiện tại hoàn tất trước khi đổi model.",
  MODEL_ALREADY_REGISTERED: "Model này đã được đăng ký trên connection.",
  REINDEX_JOB_NOT_RETRYABLE: "Tác vụ này hiện không thể thử lại.",
  UNSUPPORTED_FILE_TYPE: "Chỉ hỗ trợ PDF, TXT và Markdown.",
  REINDEX_QUEUE_UNAVAILABLE:
    "Không thể đưa tác vụ vào hàng đợi. Hãy thử lại khi dịch vụ phục hồi.",
  PROVIDER_IN_USE: "Provider hoặc model đang được workspace sử dụng.",
  PROVIDER_CREDENTIAL_IN_USE:
    "Không thể xóa thông tin xác thực của provider đang được sử dụng.",
};
export function apiError(error: unknown): string {
  const code = (error as { error?: { error?: { code?: string } } })?.error
    ?.error?.code;
  return (
    MESSAGES[code ?? ""] ??
    "Không thể hoàn thành thao tác. Kiểm tra cấu hình rồi thử lại."
  );
}
