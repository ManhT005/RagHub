import { Injectable, computed, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { forkJoin, tap } from 'rxjs';
import { AccessApiService } from '../api/access-api.service';
import { Workspace } from '../raghub-api.service';
import { WorkspacePermission, WorkspacePermissions } from '../permissions/permission.types';

@Injectable()
export class WorkspaceContextStore {
  private readonly http = inject(HttpClient);
  private readonly access = inject(AccessApiService);
  readonly workspace = signal<Workspace | null>(null);
  readonly accessInfo = signal<WorkspacePermissions | null>(null);
  readonly isAdmin = computed(() => this.accessInfo()?.is_system_admin ?? false);
  can(permission: WorkspacePermission): boolean { return this.accessInfo()?.permissions.includes(permission) ?? false; }
  load(id: string) {
    this.clear();
    return forkJoin({
      workspace: this.http.get<Workspace>(`/api/v1/workspaces/${id}`),
      access: this.access.permissions(id),
    }).pipe(tap(({ workspace, access }) => { this.workspace.set(workspace); this.accessInfo.set(access); }));
  }
  refresh() { return this.load(this.workspace()!.id); }
  clear() { this.workspace.set(null); this.accessInfo.set(null); }
}
