export const WORKSPACE_PERMISSIONS = [
  ["workspace.view", "Xem workspace"],
  ["workspace.edit", "Chỉnh sửa workspace"],
  ["document.view", "Xem tài liệu"],
  ["document.upload", "Tải tài liệu lên"],
  ["document.reindex", "Lập chỉ mục lại"],
  ["document.delete", "Xóa tài liệu"],
  ["chat.use", "Chat với tri thức"],
  ["ai.view", "Xem cấu hình AI"],
  ["ai.change_embedding", "Đổi embedding model"],
  ["member.view", "Xem thành viên"],
  ["member.manage", "Quản lý thành viên và quyền"],
] as const;
export type WorkspacePermission = (typeof WORKSPACE_PERMISSIONS)[number][0];
export const PERMISSION_DEPENDENCIES: Partial<
  Record<WorkspacePermission, WorkspacePermission>
> = {
  "workspace.edit": "workspace.view",
  "document.upload": "document.view",
  "document.reindex": "document.view",
  "document.delete": "document.view",
  "ai.change_embedding": "ai.view",
  "member.manage": "member.view",
};
export interface WorkspacePermissions {
  workspace_id: string;
  is_system_admin: boolean;
  permissions: WorkspacePermission[];
}
export interface WorkspaceMember {
  user_id: string;
  email: string;
  display_name: string | null;
  status: string;
  permissions: WorkspacePermission[];
}
