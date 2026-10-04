import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  OnDestroy,
  inject,
  signal,
} from "@angular/core";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { FormsModule } from "@angular/forms";
import { Router, RouterLink, RouterOutlet } from "@angular/router";
import {
  WorkspaceApiService,
  WorkspaceSummary,
} from "../../core/api/workspace-api.service";
import { WorkspaceContextStore } from "../../core/workspace-context/workspace-context.store";
@Component({
  selector: "raghub-workspace-shell",
  imports: [FormsModule, RouterLink, RouterOutlet],
  template: `<div class="selfhost-page">
    <nav class="workspace-breadcrumb" aria-label="Breadcrumb">
      <a routerLink="/app/workspaces">Workspaces</a
      ><span aria-hidden="true"> / </span
      ><strong>{{ context.workspace()?.name }}</strong>
      @if (workspaces().length > 1) {
        <select
          aria-label="Đổi workspace"
          [ngModel]="context.workspace()?.id"
          (ngModelChange)="switchWorkspace($event)"
          style="margin-left:auto"
        >
          @for (item of workspaces(); track item.id) {
            <option [value]="item.id">{{ item.name }}</option>
          }
        </select>
      }
    </nav>
    <router-outlet />
  </div>`,
  styles: `
    .workspace-breadcrumb {
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 0 0 24px;
      color: var(--rh-muted);
      font-size: 13px;
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WorkspaceShellComponent implements OnDestroy {
  protected readonly context = inject(WorkspaceContextStore);
  protected readonly workspaces = signal<WorkspaceSummary[]>([]);
  private readonly router = inject(Router);
  constructor() {
    inject(WorkspaceApiService)
      .list()
      .pipe(takeUntilDestroyed(inject(DestroyRef)))
      .subscribe({ next: (items) => this.workspaces.set(items) });
  }
  protected switchWorkspace(id: string) {
    void this.router.navigate(["/app/workspaces", id, "overview"]);
  }
  ngOnDestroy() {
    this.context.clear();
  }
}
