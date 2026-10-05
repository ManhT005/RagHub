import { HttpClient } from "@angular/common/http";
import { Injectable, inject } from "@angular/core";
import { DocumentItem } from "../raghub-api.service";
export interface DocumentMetadata extends DocumentItem {
  updated_at: string | null;
  mime_type: string | null;
  size_bytes: number | null;
  chunk_count: number | null;
  indexed_at: string | null;
  embedding_model_id: string | null;
  embedding_model_name: string | null;
  embedding_dimension: number | null;
}
export interface DocumentDetail extends DocumentMetadata {
  checksum: string | null;
  chunk_strategy: string;
}
export const DOCUMENT_TERMINAL = ["READY", "FAILED"];
export const DOCUMENT_STATUSES: Record<string, string> = {
  UPLOADED: "Đã tải lên",
  QUEUED: "Đang chờ",
  PARSING: "Đang đọc",
  CHUNKING: "Đang chia chunks",
  EMBEDDING: "Đang embedding",
  INDEXING: "Đang lập index",
  READY: "Sẵn sàng",
  FAILED: "Thất bại",
};
@Injectable({ providedIn: "root" })
export class DocumentApiService {
  private readonly http = inject(HttpClient);
  list(id: string) {
    return this.http.get<DocumentMetadata[]>(
      `/api/v1/workspaces/${id}/documents`,
    );
  }
  detail(id: string, doc: string) {
    return this.http.get<DocumentDetail>(
      `/api/v1/workspaces/${id}/documents/${doc}`,
    );
  }
  download(id: string, doc: string) {
    return this.http.get(`/api/v1/workspaces/${id}/documents/${doc}/download`, {
      responseType: "blob",
    });
  }
}
