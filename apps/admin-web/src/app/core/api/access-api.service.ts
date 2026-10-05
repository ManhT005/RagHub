import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { WorkspaceMember, WorkspacePermission, WorkspacePermissions } from '../permissions/permission.types';

@Injectable({ providedIn: 'root' })
export class AccessApiService {
  private readonly http = inject(HttpClient);
  private base(id: string) { return `/api/v1/workspaces/${id}`; }
  permissions(id: string) { return this.http.get<WorkspacePermissions>(`${this.base(id)}/me/permissions`); }
  members(id: string) { return this.http.get<WorkspaceMember[]>(`${this.base(id)}/members`); }
  candidates(id: string) { return this.http.get<WorkspaceMember[]>(`${this.base(id)}/members/candidates`); }
  assign(id: string, userId: string, permissions: WorkspacePermission[]) {
    return this.http.post<WorkspaceMember>(`${this.base(id)}/members`, { user_id: userId, permissions });
  }
  update(id: string, userId: string, permissions: WorkspacePermission[]) {
    return this.http.patch<WorkspaceMember>(`${this.base(id)}/members/${userId}`, { permissions });
  }
  remove(id: string, userId: string) { return this.http.delete(`${this.base(id)}/members/${userId}`); }
}
