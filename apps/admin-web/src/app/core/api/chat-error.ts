const CHAT_ERRORS: Record<string, string> = {
  PROVIDER_AUTH_FAILED: "API key của Chat/Embedding provider không hợp lệ. Kiểm tra cấu hình AI của workspace.",
  PROVIDER_RATE_LIMITED: "Provider đang giới hạn tốc độ hoặc quota. Hãy thử lại sau.",
  PROVIDER_TIMEOUT: "Provider phản hồi quá lâu. Hãy thử lại.",
  CHAT_PROVIDER_TIMEOUT: "Provider phản hồi quá lâu. Hãy thử lại.",
  PROVIDER_UNAVAILABLE: "Provider hiện không truy cập được. Kiểm tra kết nối và endpoint.",
  PROVIDER_UNREACHABLE: "Không thể kết nối provider. Kiểm tra endpoint và dịch vụ.",
  PROVIDER_INVALID_RESPONSE: "Provider trả dữ liệu không hợp lệ. Kiểm tra model và cấu hình AI.",
  SEARCH_UNAVAILABLE: "Vector search hiện không khả dụng. Kiểm tra dịch vụ tìm kiếm.",
  PROVIDER_NOT_CONFIGURED: "Workspace chưa có cấu hình AI hợp lệ. Hãy chọn Chat và Embedding provider.",
  CHAT_RUNTIME_FAILED: "Chat runtime gặp lỗi ngoài dự kiến. Hãy thử lại.",
  CHATBOT_NOT_PUBLISHED: "Chatbot chưa được xuất bản cho truy cập công khai.",
  WORKSPACE_PERMISSION_DENIED: "Bạn chưa có quyền sử dụng chat trong workspace này.",
  CHAT_CONNECTION_FAILED: "Kết nối chat bị gián đoạn. Hãy thử lại.",
};

export function chatError(data: Record<string, unknown>): string {
  const code = typeof data["code"] === "string" ? data["code"] : "";
  const message = CHAT_ERRORS[code] ?? "Không thể tạo câu trả lời. Kiểm tra cấu hình AI rồi thử lại.";
  return /^[A-Z][A-Z0-9_]{0,79}$/.test(code) ? `${message} Mã lỗi: ${code}` : message;
}
