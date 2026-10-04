import { HttpClient } from "@angular/common/http";
import { Injectable, inject } from "@angular/core";
import { Workspace, WorkspaceProviderBinding } from "../raghub-api.service";

export interface EmbeddingProfile {
  id: string;
  model: string;
  provider_name: string;
  provider_type: string;
  dimension: number;
  status: string;
}
export interface WorkspaceSummary extends Workspace {
  member_count: number;
  document_count: number;
  chunk_count: number | null;
  last_indexed_at: string | null;
  embedding_model: EmbeddingProfile | null;
  chat_provider_id: string | null;
  created_at: string;
  updated_at: string | null;
  status: string;
  reindex_job_id: string | null;
  reindex_status: string | null;
}
export interface EmbeddingPreview {
  current_model: {
    id: string;
    model: string;
    dimension: number;
    provider_type: string;
  } | null;
  target_model: {
    id: string;
    model: string;
    dimension: number;
    provider_type: string;
  };
  requires_reindex: boolean;
  documents_affected: number;
  chunks_affected: number | null;
}
export interface ReindexJob {
  id: string;
  workspace_id: string;
  status: string;
  total_documents: number;
  processed_documents: number;
  failed_documents: number;
  error_code: string | null;
}
export const REINDEX_TERMINAL = [
  "COMPLETED",
  "FAILED",
  "QUEUE_FAILED",
  "SUPERSEDED",
];
@Injectable({ providedIn: "root" })
export class WorkspaceApiService {
  private readonly http = inject(HttpClient);
  list() {
    return this.http.get<WorkspaceSummary[]>("/api/v1/workspaces");
  }
  get(id: string) {
    return this.http.get<WorkspaceSummary>(`/api/v1/workspaces/${id}`);
  }
  create(name: string, slug: string) {
    return this.http.post<WorkspaceSummary>("/api/v1/workspaces", {
      name,
      slug,
    });
  }
  update(id: string, name: string, slug: string) {
    return this.http.patch<WorkspaceSummary>(`/api/v1/workspaces/${id}`, {
      name,
      slug,
    });
  }
  remove(id: string) {
    return this.http.delete(`/api/v1/workspaces/${id}`);
  }
  preview(id: string, modelId: string) {
    return this.http.post<EmbeddingPreview>(
      `/api/v1/workspaces/${id}/embedding-model/preview`,
      { model_id: modelId },
    );
  }
  changeEmbedding(id: string, modelId: string) {
    return this.http.put<WorkspaceProviderBinding>(
      `/api/v1/workspaces/${id}/embedding-model`,
      { model_id: modelId },
    );
  }
  changeChat(id: string, modelId: string) {
    return this.http.put<WorkspaceProviderBinding>(
      `/api/v1/workspaces/${id}/chat-model`,
      { model_id: modelId },
    );
  }
  reindexJob(id: string, jobId: string) {
    return this.http.get<ReindexJob>(
      `/api/v1/workspaces/${id}/embedding-reindex-jobs/${jobId}`,
    );
  }
  retryReindex(jobId: string) {
    return this.http.post(`/api/v1/embedding-reindex-jobs/${jobId}/retry`, {});
  }
}
