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
import { ProviderLogoComponent } from "../../shared/provider-logo/provider-logo.component";
import { shortModelName } from "../../core/provider-brand/provider-brand.registry";
import { NzTagModule } from "ng-zorro-antd/tag";
@Component({
  selector: "raghub-workspace-overview",
  imports: [
    NzTagModule,
    ProviderLogoComponent,
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
      <section class="workspace-summary" aria-label="Tóm tắt workspace">
        <div class="summary-model">
          <p class="eyebrow">Embedding model của workspace</p>
          @if (workspace.embedding_model; as model) {
            <div class="provider-model">
              <raghub-provider-logo
                [catalogId]="model.provider_catalog_id"
                size="lg"
              />
              <div class="summary-model-identity">
                <strong [title]="model.model"
                  >{{ model.provider_name }} /
                  {{ shortModelName(model.model) }}</strong
                >
                <div class="model-badges">
                  <nz-tag>{{
                    model.provider_catalog_id === "sentence-transformer" ||
                    model.provider_catalog_id === "ollama"
                      ? "Local"
                      : model.provider_catalog_id === "compatible" ||
                          !model.provider_catalog_id
                        ? "Custom"
                        : "Cloud"
                  }}</nz-tag
                  ><nz-tag>{{ model.dimension }} dims</nz-tag
                  ><nz-tag
                    [nzColor]="
                      model.status === 'AVAILABLE' ? 'green' : 'default'
                    "
                    >{{
                      model.status === "AVAILABLE"
                        ? "Hoạt động"
                        : model.status === "UNTESTED"
                          ? "Chưa kiểm tra"
                          : "Cần kiểm tra"
                    }}</nz-tag
                  >
                </div>
              </div>
            </div>
          } @else {
            <p>Chưa cấu hình</p>
          }
          @if (context.can("ai.view")) {
            <a routerLink="../ai">AI &amp; Models →</a>
          }
        </div>
        <div class="summary-stat">
          <strong>{{ workspace.document_count }}</strong>
          <span class="muted"
            >Tài liệu · {{ workspace.chunk_count ?? "—" }} chunks</span
          >
          @if (context.can("document.view")) {
            <a routerLink="../documents">Xem tài liệu →</a>
          }
        </div>
        <div class="summary-stat">
          <strong>{{ workspace.member_count }}</strong>
          <span class="muted">Thành viên</span>
          @if (context.can("member.view")) {
            <a routerLink="../members">Thành viên & quyền →</a>
          }
        </div>
        <div class="summary-stat">
          <strong>
            {{
              workspace.last_indexed_at
                ? (workspace.last_indexed_at | date: "dd/MM/yyyy HH:mm")
                : "Chưa lập chỉ mục"
            }}
          </strong>
          <span class="muted">Lần lập chỉ mục gần nhất</span>
          <nz-tag
            [nzColor]="
              workspace.status === 'ACTIVE'
                ? 'green'
                : workspace.status === 'REINDEXING'
                  ? 'blue'
                  : 'default'
            "
            >{{
              workspace.status === "ACTIVE"
                ? "Hoạt động"
                : workspace.status === "REINDEXING"
                  ? "Đang lập chỉ mục"
                  : workspace.status === "AI_NOT_CONFIGURED"
                    ? "AI chưa cấu hình"
                    : "Cần kiểm tra"
            }}</nz-tag
          >
        </div>
      </section>
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
  styleUrl: "./workspace-overview.component.css",
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WorkspaceOverviewComponent {
  protected readonly shortModelName = shortModelName;
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
