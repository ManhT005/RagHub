import { DatePipe } from "@angular/common";
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  signal,
  untracked,
} from "@angular/core";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { FormsModule } from "@angular/forms";
import { NzButtonModule } from "ng-zorro-antd/button";
import { NzAlertModule } from "ng-zorro-antd/alert";
import { NzInputModule } from "ng-zorro-antd/input";
import { NzModalModule } from "ng-zorro-antd/modal";
import { NzDrawerModule } from "ng-zorro-antd/drawer";
import { NzTableModule } from "ng-zorro-antd/table";
import { NzTagModule } from "ng-zorro-antd/tag";
import { NzDropDownModule } from "ng-zorro-antd/dropdown";
import { NzPopconfirmModule } from "ng-zorro-antd/popconfirm";
import {
  EMPTY,
  Subscription,
  catchError,
  concatMap,
  exhaustMap,
  finalize,
  from,
  of,
  takeWhile,
  timer,
  toArray,
} from "rxjs";
import {
  DocumentApiService,
  DocumentDetail,
  DocumentMetadata,
  DOCUMENT_STATUSES,
  DOCUMENT_TERMINAL,
} from "../../core/api/document-api.service";
import { WorkspaceContextStore } from "../../core/workspace-context/workspace-context.store";
import { RaghubApiService } from "../../core/raghub-api.service";
import { apiError } from "../../core/api/api-error";
import { ingestionErrorMessage } from "../../documents/ingestion-errors";
import { EmbeddingProfileComponent } from "../workspace-ai/embedding-profile.component";

@Component({
  selector: "raghub-workspace-documents",
  imports: [
    DatePipe,
    FormsModule,
    NzButtonModule,
    NzAlertModule,
    NzInputModule,
    NzModalModule,
    NzDrawerModule,
    NzTableModule,
    NzTagModule,
    NzDropDownModule,
    NzPopconfirmModule,
    EmbeddingProfileComponent,
  ],
  templateUrl: "./workspace-documents.component.html",
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WorkspaceDocumentsComponent {
  protected readonly context = inject(WorkspaceContextStore);
  protected readonly documents = signal<DocumentMetadata[]>([]);
  protected readonly loading = signal(false);
  protected readonly error = signal("");
  protected readonly notice = signal("");
  protected readonly busy = signal(false);
  protected readonly search = signal("");
  protected readonly status = signal("");
  protected readonly fileType = signal("");
  protected readonly uploadOpen = signal(false);
  protected readonly files = signal<File[]>([]);
  protected readonly detailOpen = signal(false);
  protected readonly detailLoading = signal(false);
  protected readonly detail = signal<DocumentDetail | null>(null);
  protected readonly statuses = Object.entries(DOCUMENT_STATUSES);
  protected readonly ingestionError = ingestionErrorMessage;
  protected readonly filtered = computed(() =>
    this.documents().filter(
      (doc) =>
        doc.name.toLowerCase().includes(this.search().toLowerCase()) &&
        (!this.status() || doc.status === this.status()) &&
        (!this.fileType() || this.extension(doc.name) === this.fileType()),
    ),
  );
  private readonly api = inject(DocumentApiService);
  private readonly actions = inject(RaghubApiService);
  private readonly destroyRef = inject(DestroyRef);
  private polling?: Subscription;
  private workspaceId = "";
  constructor() {
    effect(() => {
      const id = this.context.workspace()?.id ?? "";
      if (!id || id === this.workspaceId) return;
      this.workspaceId = id;
      untracked(() => this.load());
    });
  }
  protected statusLabel(status: string) {
    return DOCUMENT_STATUSES[status] ?? status;
  }
  protected statusColor(status: string) {
    return status === "READY" ? "green" : status === "FAILED" ? "red" : "blue";
  }
  protected extension(name: string) {
    return name.split(".").pop()?.toLowerCase() ?? "";
  }
  protected size(bytes: number | null) {
    return bytes === null
      ? "—"
      : bytes < 1024 * 1024
        ? `${(bytes / 1024).toFixed(1)} KB`
        : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  }
  protected uploadAllowed() {
    return (
      this.context.can("document.upload") &&
      !!this.context.workspace()?.embedding_model &&
      this.context.workspace()?.status !== "REINDEXING"
    );
  }
  protected load() {
    this.polling?.unsubscribe();
    this.loading.set(true);
    this.api
      .list(this.workspaceId)
      .pipe(
        finalize(() => this.loading.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (items) => {
          this.documents.set(items);
          if (items.some((doc) => !DOCUMENT_TERMINAL.includes(doc.status)))
            this.poll();
        },
        error: (error) => this.error.set(apiError(error)),
      });
  }
  private poll() {
    this.polling = timer(3000, 3000)
      .pipe(
        exhaustMap(() => this.api.list(this.workspaceId)),
        takeWhile(
          (items) =>
            items.some((doc) => !DOCUMENT_TERMINAL.includes(doc.status)),
          true,
        ),
        catchError((error) => {
          this.error.set(apiError(error));
          return EMPTY;
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((items) => {
        this.documents.set(items);
        if (!items.some((doc) => !DOCUMENT_TERMINAL.includes(doc.status)))
          this.context
            .refresh()
            .pipe(takeUntilDestroyed(this.destroyRef))
            .subscribe({ error: (error) => this.error.set(apiError(error)) });
      });
  }
  protected chooseFiles(event: Event) {
    const input = event.target as HTMLInputElement,
      files = Array.from(input.files ?? []);
    input.value = "";
    this.files.set([]);
    this.error.set("");
    if (files.some((file) => file.size > 25 * 1024 * 1024)) {
      this.error.set("Mỗi tệp phải nhỏ hơn hoặc bằng 25 MB.");
      return;
    }
    if (
      files.some(
        (file) => !["pdf", "txt", "md"].includes(this.extension(file.name)),
      )
    ) {
      this.error.set("Chỉ hỗ trợ PDF, TXT và Markdown (.md).");
      return;
    }
    if (files.some((file) => !file.size)) {
      this.error.set("Tệp tải lên không được để trống.");
      return;
    }
    this.files.set(files);
  }
  protected upload() {
    if (this.busy() || !this.files().length || !this.uploadAllowed()) return;
    this.busy.set(true);
    this.error.set("");
    this.notice.set("");
    const failed: File[] = [];
    from(this.files())
      .pipe(
        concatMap((file) =>
          this.actions.upload(this.workspaceId, file).pipe(
            catchError((error) => {
              failed.push(file);
              this.error.set(apiError(error));
              return of(null);
            }),
          ),
        ),
        toArray(),
        finalize(() => this.busy.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => {
        const uploaded = this.files().length - failed.length;
        this.files.set(failed);
        if (!failed.length) this.uploadOpen.set(false);
        if (uploaded) {
          this.notice.set(
            `Đã tải lên ${uploaded} tài liệu. Hệ thống đang xử lý.`,
          );
          this.load();
          this.refreshSummary();
        }
      });
  }
  protected showDetail(doc: DocumentMetadata) {
    this.detailOpen.set(true);
    this.detail.set(null);
    this.detailLoading.set(true);
    this.error.set("");
    this.api
      .detail(this.workspaceId, doc.id)
      .pipe(
        finalize(() => this.detailLoading.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (item) => this.detail.set(item),
        error: (error) => this.error.set(apiError(error)),
      });
  }
  protected download(doc: DocumentMetadata) {
    if (this.busy()) return;
    this.busy.set(true);
    this.error.set("");
    this.api
      .download(this.workspaceId, doc.id)
      .pipe(
        finalize(() => this.busy.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (blob) => {
          const url = URL.createObjectURL(blob),
            anchor = document.createElement("a");
          anchor.href = url;
          anchor.download = doc.name;
          anchor.click();
          URL.revokeObjectURL(url);
        },
        error: (error) => this.error.set(apiError(error)),
      });
  }
  protected reindex(doc: DocumentMetadata, retry = false) {
    if (
      !doc.document_version_id ||
      this.busy() ||
      !this.context.can("document.reindex") ||
      (!retry && doc.status !== "READY") ||
      (retry && !doc.retryable)
    )
      return;
    this.busy.set(true);
    this.error.set("");
    const request = retry
      ? this.actions.retryDocument(this.workspaceId, doc.document_version_id)
      : this.actions.reindexDocument(this.workspaceId, doc.document_version_id);
    request
      .pipe(
        finalize(() => this.busy.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: () => {
          this.notice.set("Đã đưa tài liệu vào hàng đợi xử lý.");
          this.load();
        },
        error: (error) => this.error.set(apiError(error)),
      });
  }
  protected remove(doc: DocumentMetadata) {
    if (this.busy() || !this.context.can("document.delete")) return;
    this.busy.set(true);
    this.error.set("");
    this.actions
      .deleteDocument(this.workspaceId, doc.id)
      .pipe(
        finalize(() => this.busy.set(false)),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: () => {
          this.notice.set("Đã xóa tài liệu.");
          this.load();
          this.refreshSummary();
        },
        error: (error) => this.error.set(apiError(error)),
      });
  }
  private refreshSummary() {
    this.context
      .refresh()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({ error: (error) => this.error.set(apiError(error)) });
  }
}
