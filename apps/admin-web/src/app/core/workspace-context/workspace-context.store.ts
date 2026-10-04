import { Injectable, computed, inject, signal } from "@angular/core";
import { catchError, forkJoin, tap, throwError } from "rxjs";
import { AccessApiService } from "../api/access-api.service";
import {
  WorkspaceApiService,
  WorkspaceSummary,
} from "../api/workspace-api.service";
import {
  WorkspacePermission,
  WorkspacePermissions,
} from "../permissions/permission.types";

@Injectable({ providedIn: "root" })
export class WorkspaceContextStore {
  private readonly api = inject(WorkspaceApiService);
  private readonly access = inject(AccessApiService);
  readonly workspace = signal<WorkspaceSummary | null>(null);
  readonly accessInfo = signal<WorkspacePermissions | null>(null);
  readonly isAdmin = computed(
    () => this.accessInfo()?.is_system_admin ?? false,
  );
  can(permission: WorkspacePermission): boolean {
    return this.accessInfo()?.permissions.includes(permission) ?? false;
  }
  load(id: string) {
    this.clear();
    return forkJoin({
      workspace: this.api.get(id),
      access: this.access.permissions(id),
    }).pipe(
      tap(({ workspace, access }) => {
        this.workspace.set(workspace);
        this.accessInfo.set(access);
      }),
    );
  }
  refresh() {
    const id = this.workspace()!.id;
    return forkJoin({
      workspace: this.api.get(id),
      access: this.access.permissions(id),
    }).pipe(
      tap(({ workspace, access }) => {
        this.workspace.set(workspace);
        this.accessInfo.set(access);
      }),
      catchError((error) => {
        if ([401, 403, 404].includes(error.status)) this.clear();
        return throwError(() => error);
      }),
    );
  }
  clear() {
    this.workspace.set(null);
    this.accessInfo.set(null);
  }
}
