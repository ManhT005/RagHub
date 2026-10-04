import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  effect,
  inject,
  signal,
} from "@angular/core";
import { FormsModule } from "@angular/forms";
import { NzButtonModule } from "ng-zorro-antd/button";
import { NzModalModule } from "ng-zorro-antd/modal";
import { NzTableModule } from "ng-zorro-antd/table";
import { NzAlertModule } from "ng-zorro-antd/alert";
import { NzPopconfirmModule } from "ng-zorro-antd/popconfirm";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { finalize, forkJoin, of } from "rxjs";
import { WorkspaceContextStore } from "../../core/workspace-context/workspace-context.store";
import { AccessApiService } from "../../core/api/access-api.service";
import {
  PERMISSION_DEPENDENCIES,
  WORKSPACE_PERMISSIONS,
  WorkspacePermission,
  WorkspaceMember,
} from "../../core/permissions/permission.types";
import { apiError } from "../../core/api/api-error";

@Component({
  selector: "raghub-workspace-members",
  imports: [
    FormsModule,
    NzButtonModule,
    NzModalModule,
    NzTableModule,
    NzAlertModule,
    NzPopconfirmModule,
  ],
  templateUrl: "./workspace-members.component.html",
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WorkspaceMembersComponent {
  protected readonly context = inject(WorkspaceContextStore);
  protected readonly members = signal<WorkspaceMember[]>([]);
  protected readonly candidates = signal<WorkspaceMember[]>([]);
  protected readonly loading = signal(false);
  protected readonly saving = signal(false);
  protected readonly error = signal("");
  protected readonly editorOpen = signal(false);
  protected readonly permissions = WORKSPACE_PERMISSIONS;
  protected selectedUserId = "";
  protected grants: WorkspacePermission[] = ["workspace.view"];
  private editing = false;
  private readonly api = inject(AccessApiService);
  private readonly destroyRef = inject(DestroyRef);

  constructor() {
    effect((onCleanup) => {
      const id = this.context.workspace()?.id;
      if (!id) return;
      const request = this.load(id);
      onCleanup(() => request.unsubscribe());
    });
  }

  protected load(id = this.context.workspace()!.id) {
    this.loading.set(true);
    return forkJoin({
      members: this.api.members(id),
      candidates: this.context.can("member.manage")
        ? this.api.candidates(id)
        : of([]),
    })
      .pipe(
        finalize(() => this.loading.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (data) => {
          this.members.set(data.members);
          this.candidates.set(data.candidates);
        },
        error: (error) => this.error.set(apiError(error)),
      });
  }

  protected open(member?: WorkspaceMember) {
    this.editing = !!member;
    this.selectedUserId = member?.user_id ?? "";
    this.grants = member ? [...member.permissions] : ["workspace.view"];
    this.error.set("");
    this.editorOpen.set(true);
  }
  protected selectUser() {
    const member = this.members().find(
      (item) => item.user_id === this.selectedUserId,
    );
    this.editing = !!member;
    this.grants = member ? [...member.permissions] : ["workspace.view"];
  }
  protected toggle(permission: WorkspacePermission, checked: boolean) {
    const selected = new Set(this.grants);
    if (checked) {
      selected.add(permission);
      const dependency = PERMISSION_DEPENDENCIES[permission];
      if (dependency) selected.add(dependency);
    } else {
      selected.delete(permission);
      for (const [dependent, view] of Object.entries(PERMISSION_DEPENDENCIES))
        if (view === permission)
          selected.delete(dependent as WorkspacePermission);
    }
    selected.add("workspace.view");
    this.grants = [...selected];
  }
  protected save() {
    if (
      !this.selectedUserId ||
      this.saving() ||
      !this.context.can("member.manage")
    )
      return;
    this.saving.set(true);
    this.error.set("");
    const id = this.context.workspace()!.id;
    const request = this.editing
      ? this.api.update(id, this.selectedUserId, this.grants)
      : this.api.assign(id, this.selectedUserId, this.grants);
    request
      .pipe(
        finalize(() => this.saving.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: () => {
          this.editorOpen.set(false);
          this.context
            .refresh()
            .pipe(takeUntilDestroyed(this.destroyRef))
            .subscribe({
              next: () => this.load(),
              error: (error) => this.error.set(apiError(error)),
            });
        },
        error: (error) => this.error.set(apiError(error)),
      });
  }
  protected remove(member: WorkspaceMember) {
    if (this.saving() || !this.context.can("member.manage")) return;
    this.saving.set(true);
    this.api
      .remove(this.context.workspace()!.id, member.user_id)
      .pipe(
        finalize(() => this.saving.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: () => this.load(),
        error: (error) => this.error.set(apiError(error)),
      });
  }
}
