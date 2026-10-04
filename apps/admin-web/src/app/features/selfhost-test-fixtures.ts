import { signal } from "@angular/core";
import { of } from "rxjs";
import { WorkspaceSummary } from "../core/api/workspace-api.service";
import {
  WorkspacePermission,
  WorkspacePermissions,
} from "../core/permissions/permission.types";
export const workspaceFixture: WorkspaceSummary = {
  id: "workspace-1",
  organization_id: "org-1",
  name: "Knowledge",
  slug: "knowledge",
  member_count: 1,
  document_count: 1,
  chunk_count: 3,
  last_indexed_at: null,
  embedding_model: {
    id: "model-1",
    model: "current-model",
    provider_name: "Local",
    provider_type: "LOCAL_SENTENCE_TRANSFORMER",
    dimension: 384,
    status: "ACTIVE",
  },
  chat_provider_id: null,
  created_at: "2026-10-04T00:00:00Z",
  updated_at: null,
  status: "ACTIVE",
  reindex_job_id: null,
  reindex_status: null,
};
export function contextFixture(permissions: WorkspacePermission[]) {
  const accessInfo = signal<WorkspacePermissions>({
    workspace_id: workspaceFixture.id,
    is_system_admin: false,
    permissions,
  });
  return {
    workspace: signal<WorkspaceSummary | null>({ ...workspaceFixture }),
    accessInfo,
    can: (permission: WorkspacePermission) =>
      accessInfo().permissions.includes(permission),
    isAdmin: () => accessInfo().is_system_admin,
    refresh: vi.fn(() => of({})),
    clear: vi.fn(),
    load: vi.fn(() => of({})),
  };
}
