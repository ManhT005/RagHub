import { DocumentMetadata, DOCUMENT_STATUSES, DOCUMENT_TERMINAL } from "../core/api/document-api.service";

export function processingLabel(doc: DocumentMetadata): string {
  if (DOCUMENT_TERMINAL.includes(doc.status)) return DOCUMENT_STATUSES[doc.status];
  switch (doc.waiting_reason) {
    case "WAITING_FOR_WORKER": return "Đang chờ worker";
    case "PROVIDER_RATE_LIMIT": return "Đang chờ API";
    case "WAITING_FOR_QUOTA": return "Đang chờ quota";
    case "QUOTA_COORDINATOR_UNAVAILABLE": return "Đang chờ điều phối quota";
    case "PROVIDER_TIMEOUT_RETRY": return "Đang thử lại API";
    case "WAITING_FOR_PROVIDER": return "Đang chờ API";
    case "STORAGE_UNAVAILABLE": return "Đang thử lại lưu trữ";
    case "INDEX_UNAVAILABLE": return "Đang thử lại lập chỉ mục";
    default: return DOCUMENT_STATUSES[doc.stage ?? doc.status] ?? doc.status;
  }
}

export function waitMessage(doc: DocumentMetadata, now: number): string {
  const reason = doc.waiting_reason;
  if (!reason || DOCUMENT_TERMINAL.includes(doc.status)) return "";
  const explanation: Record<string, string> = {
    PROVIDER_RATE_LIMIT: "Provider đang giới hạn tốc độ.",
    WAITING_FOR_QUOTA: "Đang chờ quota embedding khả dụng.",
    QUOTA_COORDINATOR_UNAVAILABLE: "Điều phối quota tạm thời chưa khả dụng.",
    PROVIDER_TIMEOUT_RETRY: "API phản hồi quá chậm; hệ thống sẽ tự thử lại.",
    WAITING_FOR_PROVIDER: "Provider tạm thời chưa khả dụng.",
    WAITING_FOR_WORKER: "Tài liệu đang chờ worker xử lý.",
    STORAGE_UNAVAILABLE: "Kho lưu trữ tạm thời chưa khả dụng.",
    INDEX_UNAVAILABLE: "Dịch vụ chỉ mục tạm thời chưa khả dụng.",
  };
  const seconds = doc.retry_at ? Math.max(0, Math.ceil((Date.parse(doc.retry_at) - now) / 1000)) : null;
  const retry = seconds === null ? "" : seconds > 0
    ? ` Hệ thống sẽ tự tiếp tục sau ${seconds} giây.` : " Đang chờ hệ thống tiếp tục.";
  return (explanation[reason] ?? "Đang chờ xử lý.") + retry;
}

export function documentPollDelay(docs: DocumentMetadata[], now = Date.now()): number | null {
  const active = docs.filter(doc => !DOCUMENT_TERMINAL.includes(doc.status));
  if (!active.length) return null;
  if (active.some(doc => !["WAITING_QUOTA", "WAITING_PROVIDER", "RETRYING"].includes(doc.work_state ?? ""))) return 3000;
  const dates = active.map(doc => doc.retry_at ? Date.parse(doc.retry_at) - now : 10000);
  return Math.min(10000, Math.max(2000, Math.min(...dates)));
}
