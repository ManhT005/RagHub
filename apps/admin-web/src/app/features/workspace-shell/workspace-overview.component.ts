import { DatePipe } from "@angular/common";
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  inject,
  signal,
} from "@angular/core";
import { RouterLink, ActivatedRoute } from "@angular/router";
import { FormsModule } from "@angular/forms";
import { NzButtonModule } from "ng-zorro-antd/button";
import { NzModalModule } from "ng-zorro-antd/modal";
import { NzInputModule } from "ng-zorro-antd/input";
import { NzAlertModule } from "ng-zorro-antd/alert";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { finalize, switchMap } from "rxjs";
import { WorkspaceContextStore } from "../../core/workspace-context/workspace-context.store";
import { WorkspaceApiService } from "../../core/api/workspace-api.service";
import { apiError } from "../../core/api/api-error";
@Component({
  selector: "raghub-workspace-overview",
  imports: [
    DatePipe,
    RouterLink,
    FormsModule,
    NzButtonModule,
    NzModalModule,
    NzInputModule,
    NzAlertModule,
  ],
  template: `<section class="selfhost-page">
    <header class="page-heading">
      <div>
        <h1>{{ context.workspace()?.name }}</h1>
        <p>
          {{
            context.isAdmin()
              ? "Quản trị workspace"
              : "Bạn chỉ có quyền được cấp trong workspace này."
          }}
        </p>
      </div>
      @if (context.can("workspace.edit")) {
        <button nz-button (click)="open()">Chỉnh sửa workspace</button>
      }
    </header>
    @if (error()) {
      <nz-alert nzType="error" [nzMessage]="error()" nzShowIcon />
    }
    @if (context.workspace(); as workspace) {
      <div class="summary-grid">
        <article class="surface">
          <p class="muted">Embedding đang phục vụ</p>
          <h2>{{ workspace.embedding_model?.model || "Chưa cấu hình" }}</h2>
          <p>
            {{ workspace.embedding_model?.provider_name }}
            @if (workspace.embedding_model) {
              · {{ workspace.embedding_model.dimension }} dims
            }
          </p>
          @if (context.can("ai.view")) {
            <a routerLink="../ai">Cài đặt AI →</a>
          }
        </article>
        <article class="surface">
          <p class="muted">Tài liệu</p>
          <h2>{{ workspace.document_count }}</h2>
          <p>{{ workspace.chunk_count ?? "—" }} chunks</p>
          @if (context.can("document.view")) {
            <a routerLink="../documents">Xem tài liệu →</a>
          }
        </article>
        <article class="surface">
          <p class="muted">Thành viên</p>
          <h2>{{ workspace.member_count }}</h2>
          @if (context.can("member.view")) {
            <a routerLink="../members">Thành viên & quyền →</a>
          }
        </article>
        <article class="surface">
          <p class="muted">Lần lập chỉ mục gần nhất</p>
          <h2>
            {{
              workspace.last_indexed_at
                ? (workspace.last_indexed_at | date: "dd/MM/yyyy HH:mm")
                : "Chưa lập chỉ mục"
            }}
          </h2>
          <p>{{ workspace.status }}</p>
        </article>
      </div>
    }
    <nz-modal
      [nzVisible]="editorOpen()"
      nzTitle="Chỉnh sửa workspace"
      nzOkText="Lưu"
      nzCancelText="Hủy"
      [nzOkLoading]="saving()"
      [nzOkDisabled]="!name.trim() || !slug.trim()"
      (nzOnOk)="save()"
      (nzOnCancel)="!saving() && editorOpen.set(false)"
      ><ng-container *nzModalContent
        ><label
          >Tên workspace<input
            nz-input
            [(ngModel)]="name"
            maxlength="200" /></label
        ><label
          >Mã định danh<input nz-input [(ngModel)]="slug" maxlength="100"
        /></label>
        @if (error()) {
          <p role="alert">{{ error() }}</p>
        }
      </ng-container></nz-modal
    >
  </section>`,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WorkspaceOverviewComponent {
  protected readonly context = inject(WorkspaceContextStore);
  protected readonly editorOpen = signal(false);
  protected readonly saving = signal(false);
  protected readonly error = signal("");
  protected name = "";
  protected slug = "";
  private readonly api = inject(WorkspaceApiService);
  private readonly destroyRef = inject(DestroyRef);
  constructor() {
    if (inject(ActivatedRoute).snapshot.queryParamMap.get("denied"))
      this.error.set("Bạn không có quyền truy cập chức năng này.");
  }
  protected open() {
    this.name = this.context.workspace()!.name;
    this.slug = this.context.workspace()!.slug;
    this.editorOpen.set(true);
  }
  protected save() {
    if (this.saving()) return;
    this.saving.set(true);
    this.api
      .update(this.context.workspace()!.id, this.name, this.slug)
      .pipe(
        switchMap(() => this.context.refresh()),
        finalize(() => this.saving.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: () => this.editorOpen.set(false),
        error: (error) => this.error.set(apiError(error)),
      });
  }
}
