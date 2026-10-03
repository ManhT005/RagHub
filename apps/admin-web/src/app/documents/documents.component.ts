import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  inject,
  signal,
} from "@angular/core";
import { DatePipe } from "@angular/common";
import { FormsModule } from "@angular/forms";
import { ActivatedRoute } from "@angular/router";
import { takeUntilDestroyed } from "@angular/core/rxjs-interop";
import { timer } from "rxjs";
import { NzButtonModule } from "ng-zorro-antd/button";
import { NzModalModule } from "ng-zorro-antd/modal";
import { NzSelectModule } from "ng-zorro-antd/select";
import { NzTableModule } from "ng-zorro-antd/table";
import { NzTagModule } from "ng-zorro-antd/tag";
import { NzUploadFile, NzUploadModule } from "ng-zorro-antd/upload";

import {
  RaghubApiService,
  DocumentItem,
  Workspace,
} from "../core/raghub-api.service";
import { ingestionErrorMessage } from "./ingestion-errors";

@Component({
  selector: "raghub-documents",
  imports: [
    DatePipe,
    FormsModule,
    NzButtonModule,
    NzModalModule,
    NzSelectModule,
    NzTableModule,
    NzTagModule,
    NzUploadModule,
  ],
  templateUrl: "./documents.component.html",
  styleUrl: "./documents.component.css",
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DocumentsComponent {
  protected readonly errorMessage = ingestionErrorMessage;
  protected readonly statusLabel = (status: string): string =>
    ({
      QUEUED: "Đang chờ",
      PARSING: "Đang đọc tài liệu",
      CHUNKING: "Đang chia đoạn",
      EMBEDDING: "Đang tạo embedding",
      INDEXING: "Đang lập chỉ mục",
      READY: "Sẵn sàng",
      FAILED: "Thất bại",
    })[status] ?? status;
  protected readonly statusColor = (status: string): string =>
    status === "READY" ? "green" : status === "FAILED" ? "red" : "blue";
  protected readonly workspaces = signal<Workspace[]>([]);
  protected readonly documents = signal<DocumentItem[]>([]);
  protected readonly error = signal("");
  protected readonly reindexingVersionId = signal("");
  protected readonly uploadDialogOpen = signal(false);
  protected readonly selectedFile = signal<File | null>(null);
  protected readonly uploading = signal(false);
  protected workspaceId = "";
  protected readonly beforeUpload = (file: NzUploadFile): boolean => {
    this.selectedFile.set((file.originFileObj ?? file) as File);
    return false;
  };
  private readonly api = inject(RaghubApiService);
  private readonly requestedWorkspaceId =
    inject(ActivatedRoute, { optional: true })?.snapshot.queryParamMap.get(
      "workspaceId",
    ) ?? "";
  private readonly destroyRef = inject(DestroyRef);

  constructor() {
    this.api.workspaces().subscribe({
      next: (items) => {
        this.workspaces.set(items);
        this.workspaceId =
          items.find((workspace) => workspace.id === this.requestedWorkspaceId)
            ?.id ??
          items[0]?.id ??
          "";
        this.load();
      },
      error: () => this.error.set("Hãy đăng nhập và chọn tổ chức trước."),
    });
    timer(3000, 3000)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        if (
          this.documents().some(
            (item) => !["READY", "FAILED"].includes(item.status),
          )
        )
          this.load();
      });
  }

  protected load(): void {
    if (!this.workspaceId) return;
    this.api
      .documents(this.workspaceId)
      .subscribe({
        next: (items) => this.documents.set(items),
        error: () => this.error.set("Không thể tải danh sách tài liệu."),
      });
  }
  protected openUploadDialog(): void {
    this.selectedFile.set(null);
    this.uploadDialogOpen.set(true);
  }
  protected closeUploadDialog(): void {
    if (this.uploading()) return;
    this.uploadDialogOpen.set(false);
    this.selectedFile.set(null);
  }
  protected upload(): void {
    const file = this.selectedFile();
    if (!file || !this.workspaceId) return;
    this.uploading.set(true);
    this.api.upload(this.workspaceId, file).subscribe({
      next: () => {
        this.uploading.set(false);
        this.uploadDialogOpen.set(false);
        this.selectedFile.set(null);
        this.error.set("");
        this.load();
      },
      error: (response) => {
        this.uploading.set(false);
        this.error.set(ingestionErrorMessage(response.error?.error?.code));
      },
    });
  }
  protected retry(document: DocumentItem): void {
    if (!document.document_version_id || !document.retryable) return;
    this.api
      .retryDocument(this.workspaceId, document.document_version_id)
      .subscribe({
        next: () => {
          this.error.set("");
          this.load();
        },
        error: (response) =>
          this.error.set(ingestionErrorMessage(response.error?.error?.code)),
      });
  }
  protected reindex(document: DocumentItem): void {
    if (!document.document_version_id || document.status !== "READY") return;
    this.reindexingVersionId.set(document.document_version_id);
    this.api
      .reindexDocument(this.workspaceId, document.document_version_id)
      .subscribe({
        next: () => {
          this.reindexingVersionId.set("");
          this.error.set("");
          this.load();
        },
        error: (response) => {
          this.reindexingVersionId.set("");
          this.error.set(ingestionErrorMessage(response.error?.error?.code));
        },
      });
  }
  protected remove(document: DocumentItem): void {
    this.api
      .deleteDocument(this.workspaceId, document.id)
      .subscribe({
        next: () =>
          this.documents.update((items) =>
            items.filter((item) => item.id !== document.id),
          ),
        error: () => this.error.set("Không thể xóa tài liệu."),
      });
  }
}
