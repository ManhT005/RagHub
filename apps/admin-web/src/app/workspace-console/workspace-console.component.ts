import { ChangeDetectionStrategy, Component, DestroyRef, ElementRef, computed, inject, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { timer } from 'rxjs';

import { session } from '../core/api-auth.interceptor';
import {
  Chatbot,
  DocumentItem,
  Organization,
  ProviderConfig,
  RaghubApiService,
  Workspace,
} from '../core/raghub-api.service';
import { ingestionErrorMessage } from '../documents/ingestion-errors';

@Component({
  selector: 'raghub-workspace-console',
  imports: [FormsModule, RouterLink],
  templateUrl: './workspace-console.component.html',
  styleUrl: './workspace-console.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WorkspaceConsoleComponent {
  protected readonly ingestionErrorMessage = ingestionErrorMessage;
  protected readonly organizations = signal<Organization[]>([]);
  protected readonly workspaces = signal<Workspace[]>([]);
  protected readonly providers = signal<ProviderConfig[]>([]);
  protected readonly documents = signal<DocumentItem[]>([]);
  protected readonly bots = signal<Chatbot[]>([]);
  protected readonly selectedBot = signal<Chatbot | null>(null);
  protected readonly selectedDocumentId = signal('');
  protected readonly reindexingVersionId = signal('');
  protected readonly statusLabel = (status: string): string => ({
    QUEUED: 'Đang chờ', PARSING: 'Đang đọc tài liệu', CHUNKING: 'Đang chia đoạn',
    EMBEDDING: 'Đang tạo embedding', INDEXING: 'Đang lập chỉ mục', READY: 'Sẵn sàng', FAILED: 'Thất bại',
  })[status] ?? status;
  protected readonly hasReadyDocument = computed(() =>
    this.documents().some((item) => item.status === 'READY'),
  );
  protected readonly hasChatProvider = computed(() =>
    this.providers().some((item) => item.capability === 'CHAT' && item.enabled),
  );
  protected readonly hasPublishedBot = computed(() => Boolean(this.selectedBot()?.published));
  protected readonly error = signal('');
  protected selectedOrganization = session.organizationId ?? '';
  protected selectedWorkspace = '';
  protected readonly fileInput = viewChild<ElementRef<HTMLInputElement>>('fileInput');
  private readonly api = inject(RaghubApiService);
  private readonly destroyRef = inject(DestroyRef);

  constructor() {
    this.api.organizations().subscribe({
      next: (items) => {
        this.organizations.set(items);
        if (!this.selectedOrganization && items[0]) this.selectedOrganization = items[0].id;
        this.changeOrganization();
      },
      error: () => this.error.set('Hãy đăng nhập và chọn một tổ chức trước khi mở workspace.'),
    });
    timer(3000, 3000).pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      if (this.documents().some((item) => !['READY', 'FAILED'].includes(item.status))) this.loadDocuments();
    });
  }

  protected changeOrganization(): void {
    session.organizationId = this.selectedOrganization || null;
    this.workspaces.set([]);
    this.selectedWorkspace = '';
    if (!this.selectedOrganization) return;
    this.api.workspaces().subscribe({
      next: (items) => {
        this.workspaces.set(items);
        this.selectedWorkspace = items[0]?.id ?? '';
        this.changeWorkspace();
      },
      error: () => this.error.set('Không thể tải danh sách không gian làm việc.'),
    });
  }

  protected changeWorkspace(): void {
    this.providers.set([]);
    this.documents.set([]);
    this.bots.set([]);
    this.selectedBot.set(null);
    this.selectedDocumentId.set('');
    if (!this.selectedOrganization || !this.selectedWorkspace) return;
    this.api.providers(this.selectedOrganization).subscribe({
      next: (items) => this.providers.set(items),
      error: () => this.error.set('Không thể tải cấu hình AI của tổ chức.'),
    });
    this.loadDocuments();
    this.api.chatbots(this.selectedWorkspace).subscribe({
      next: (items) => {
        this.bots.set(items);
        this.selectedBot.set(items.find((bot) => bot.published) ?? items[0] ?? null);
      },
      error: () => this.error.set('Không thể tải chatbot của workspace.'),
    });
  }

  protected upload(): void {
    const file = this.fileInput()?.nativeElement.files?.[0];
    if (!file || !this.selectedWorkspace) return;
    this.api.upload(this.selectedWorkspace, file).subscribe({
      next: () => this.loadDocuments(),
      error: (response) => this.error.set(ingestionErrorMessage(response.error?.error?.code)),
    });
  }

  protected retry(document: DocumentItem): void {
    if (!document.document_version_id || !document.retryable) return;
    this.api.retryDocument(this.selectedWorkspace, document.document_version_id).subscribe({
      next: () => this.loadDocuments(),
      error: (response) => this.error.set(ingestionErrorMessage(response.error?.error?.code)),
    });
  }

  protected reindex(document: DocumentItem): void {
    if (!document.document_version_id || document.status !== 'READY') return;
    this.reindexingVersionId.set(document.document_version_id);
    this.api.reindexDocument(this.selectedWorkspace, document.document_version_id).subscribe({
      next: () => { this.reindexingVersionId.set(''); this.loadDocuments(); },
      error: (response) => { this.reindexingVersionId.set(''); this.error.set(ingestionErrorMessage(response.error?.error?.code)); },
    });
  }

  protected remove(document: DocumentItem): void {
    if (!this.selectedWorkspace) return;
    this.api.deleteDocument(this.selectedWorkspace, document.id).subscribe({
      next: () => this.documents.update((items) => items.filter((item) => item.id !== document.id)),
      error: () => this.error.set('Không thể xóa tài liệu.'),
    });
  }

  protected selectDocument(documentId: string): void { this.selectedDocumentId.set(documentId); }

  private loadDocuments(): void {
    if (!this.selectedWorkspace) return;
    this.api.documents(this.selectedWorkspace).subscribe({
      next: (items) => this.documents.set(items),
      error: () => this.error.set('Không thể tải tài liệu của workspace.'),
    });
  }
}
