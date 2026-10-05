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
import { NzProgressModule } from "ng-zorro-antd/progress";
import { DomSanitizer, SafeResourceUrl } from "@angular/platform-browser";
import { ProviderLogoComponent } from "../../shared/provider-logo/provider-logo.component";
import { shortModelName } from "../../core/provider-brand/provider-brand.registry";
import {
  EMPTY,
  Subscription,
  Subject,
  catchError,
  concatMap,
  exhaustMap,
  finalize,
  from,
  of,
  takeWhile,
  takeUntil,
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
    NzProgressModule,
    ProviderLogoComponent,
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
  styleUrl: "./workspace-documents.component.css",
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
  protected readonly sort = signal("newest");
  protected readonly helpOpen = signal(false);
  protected readonly dragging = signal(false);
  protected readonly detailTab = signal<"info" | "content">("info");
  protected readonly contentLoading = signal(false);
  protected readonly contentError = signal("");
  protected readonly contentText = signal<string | null>(null);
  protected readonly pdfPreview = signal<SafeResourceUrl | null>(null);
  protected readonly shortModelName = shortModelName;
  protected readonly uploadOpen = signal(false);
  protected readonly files = signal<File[]>([]);
  protected readonly detailOpen = signal(false);
  protected readonly detailLoading = signal(false);
  protected readonly detail = signal<DocumentDetail | null>(null);
  protected readonly statuses = Object.entries(DOCUMENT_STATUSES);
  protected readonly ingestionError = ingestionErrorMessage;
  protected readonly filtered = computed(() =>
    this.documents()
      .filter(
        (doc) =>
          doc.name.toLowerCase().includes(this.search().toLowerCase()) &&
          (!this.status() || doc.status === this.status()) &&
          (!this.fileType() || this.extension(doc.name) === this.fileType()),
      )
      .sort((a, b) =>
        this.sort() === "name"
          ? a.name.localeCompare(b.name)
          : this.sort() === "oldest"
            ? a.created_at.localeCompare(b.created_at)
            : b.created_at.localeCompare(a.created_at),
      ),
  );
  private readonly api = inject(DocumentApiService);
  private readonly actions = inject(RaghubApiService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly sanitizer = inject(DomSanitizer);
  private readonly detailChanged = new Subject<void>();
  private previewUrl: string | null = null;
  private resumeUpload = false;
  private pendingModelPicker: EmbeddingProfileComponent | null = null;
  private polling?: Subscription;
  private readonly workspaceChanged = new Subject<void>();
  private workspaceId = "";
  constructor() {
    this.destroyRef.onDestroy(() => this.clearPreview());
    effect(() => {
      const id = this.context.workspace()?.id ?? "";
      if (id === this.workspaceId) return;
      this.workspaceChanged.next();
      this.detailChanged.next();
      this.clearPreview();
      this.resumeUpload = false;
      this.pendingModelPicker = null;
      this.workspaceId = id;
      this.documents.set([]);
      this.detail.set(null);
      this.detailOpen.set(false);
      this.files.set([]);
      this.uploadOpen.set(false);
      this.error.set("");
      this.notice.set("");
      if (id) untracked(() => this.load());
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
        takeUntil(this.workspaceChanged),
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
        takeUntil(this.workspaceChanged),
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
    this.acceptFiles(files);
  }
  protected dropFiles(event: DragEvent) {
    event.preventDefault();
    this.dragging.set(false);
    if (!this.busy())
      this.acceptFiles(Array.from(event.dataTransfer?.files ?? []));
  }
  private acceptFiles(files: File[]) {
    this.files.set([]);
    this.error.set("");
    if (files.some((file) => file.size > 25 * 1024 * 1024)) {
      this.error.set("Mỗi tệp phải nhỏ hơn hoặc bằng 25 MB.");
      return;
    }
    if (
      files.some(
        (file) => !["pdf", "txt", "md", "docx", "xlsx", "html", "htm"].includes(this.extension(file.name)),
      )
    ) {
      this.error.set("Chỉ hỗ trợ PDF, TXT, Markdown, DOCX, HTML, XLSX.");
      return;
    }
    if (files.some((file) => !file.size)) {
      this.error.set("Tệp tải lên không được để trống.");
      return;
    }
    this.files.set(files);
  }
  protected changeUploadModel(profile: EmbeddingProfileComponent) {
    this.resumeUpload = true;
    this.pendingModelPicker = profile;
    this.uploadOpen.set(false);
  }
  protected uploadDialogClosed() {
    const profile = this.pendingModelPicker;
    this.pendingModelPicker = null;
    if (!profile) return;
    if (this.context.can("ai.change_embedding")) profile.choose();
    else this.modelDialogClosed();
  }
  protected modelDialogClosed() {
    if (this.resumeUpload) this.uploadOpen.set(true);
    this.resumeUpload = false;
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
        takeUntil(this.workspaceChanged),
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
    this.detailChanged.next();
    this.clearPreview();
    this.detailTab.set("info");
    this.detailOpen.set(true);
    this.detail.set(null);
    this.detailLoading.set(true);
    this.error.set("");
    this.api
      .detail(this.workspaceId, doc.id)
      .pipe(
        finalize(() => this.detailLoading.set(false)),
        takeUntil(this.workspaceChanged),
        takeUntil(this.detailChanged),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (item) => this.detail.set(item),
        error: (error) => this.error.set(apiError(error)),
      });
  }
  protected closeDetail() {
    this.detailChanged.next();
    this.clearPreview();
    this.detailOpen.set(false);
  }
  protected navigateDetailTab(event: KeyboardEvent) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const tab =
      event.key === "Home"
        ? "info"
        : event.key === "End"
          ? "content"
          : this.detailTab() === "info"
            ? "content"
            : "info";
    if (tab === "content") this.showContent();
    else this.detailTab.set("info");
    document.getElementById(`document-${tab}-tab`)?.focus();
  }
  protected showContent() {
    this.detailTab.set("content");
    const doc = this.detail();
    if (
      !doc ||
      this.contentLoading() ||
      this.pdfPreview() ||
      this.contentText() !== null
    )
      return;
    this.contentLoading.set(true);
    this.api
      .download(this.workspaceId, doc.id)
      .pipe(
        concatMap((blob) =>
          this.extension(doc.name) === "pdf" ? of(blob) : from(blob.text()),
        ),
        finalize(() => this.contentLoading.set(false)),
        takeUntil(this.workspaceChanged),
        takeUntil(this.detailChanged),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (value) => {
          if (typeof value === "string") this.contentText.set(value);
          else {
            this.previewUrl = URL.createObjectURL(
              new Blob([value], { type: "application/pdf" }),
            );
            this.pdfPreview.set(
              this.sanitizer.bypassSecurityTrustResourceUrl(this.previewUrl),
            );
          }
        },
        error: (error) => this.contentError.set(apiError(error)),
      });
  }
  private clearPreview() {
    if (this.previewUrl) URL.revokeObjectURL(this.previewUrl);
    this.previewUrl = null;
    this.pdfPreview.set(null);
    this.contentText.set(null);
    this.contentError.set("");
  }
  protected download(doc: DocumentMetadata) {
    if (this.busy()) return;
    this.busy.set(true);
    this.error.set("");
    this.api
      .download(this.workspaceId, doc.id)
      .pipe(
        finalize(() => this.busy.set(false)),
        takeUntil(this.workspaceChanged),
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
        takeUntil(this.workspaceChanged),
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
        takeUntil(this.workspaceChanged),
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
