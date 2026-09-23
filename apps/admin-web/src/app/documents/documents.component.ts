import { ChangeDetectionStrategy, Component, DestroyRef, ElementRef, inject, signal, viewChild } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { timer } from 'rxjs';

import { RaghubApiService, DocumentItem, Workspace } from '../core/raghub-api.service';
import { ingestionErrorMessage } from './ingestion-errors';

@Component({
  selector: 'raghub-documents',
  imports: [DatePipe, FormsModule],
  templateUrl: './documents.component.html',
  styleUrl: './documents.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DocumentsComponent {
  protected readonly errorMessage = ingestionErrorMessage;
  protected readonly workspaces = signal<Workspace[]>([]);
  protected readonly documents = signal<DocumentItem[]>([]);
  protected readonly error = signal('');
  protected readonly reindexingVersionId = signal('');
  protected workspaceId = '';
  protected readonly fileInput = viewChild<ElementRef<HTMLInputElement>>('fileInput');
  private readonly api = inject(RaghubApiService);
  private readonly destroyRef = inject(DestroyRef);

  constructor() {
    this.api.workspaces().subscribe({ next: (items) => { this.workspaces.set(items); this.workspaceId = items[0]?.id ?? ''; this.load(); }, error: () => this.error.set('Select an organization and sign in first.') });
    timer(3000, 3000).pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      if (this.documents().some((item) => !['READY', 'FAILED'].includes(item.status))) this.load();
    });
  }

  protected load(): void {
    if (!this.workspaceId) return;
    this.api.documents(this.workspaceId).subscribe({ next: (items) => this.documents.set(items), error: () => this.error.set('Could not load documents.') });
  }
  protected upload(): void {
    const file = this.fileInput()?.nativeElement.files?.[0];
    if (!file || !this.workspaceId) return;
    this.api.upload(this.workspaceId, file).subscribe({ next: () => { this.error.set(''); this.load(); }, error: (response) => this.error.set(ingestionErrorMessage(response.error?.error?.code)) });
  }
  protected retry(document: DocumentItem): void {
    if (!document.document_version_id || !document.retryable) return;
    this.api.retryDocument(this.workspaceId, document.document_version_id).subscribe({
      next: () => { this.error.set(''); this.load(); },
      error: (response) => this.error.set(ingestionErrorMessage(response.error?.error?.code)),
    });
  }
  protected reindex(document: DocumentItem): void {
    if (!document.document_version_id || document.status !== 'READY') return;
    this.reindexingVersionId.set(document.document_version_id);
    this.api.reindexDocument(this.workspaceId, document.document_version_id).subscribe({
      next: () => { this.reindexingVersionId.set(''); this.error.set(''); this.load(); },
      error: (response) => { this.reindexingVersionId.set(''); this.error.set(ingestionErrorMessage(response.error?.error?.code)); },
    });
  }
  protected remove(document: DocumentItem): void {
    this.api.deleteDocument(this.workspaceId, document.id).subscribe({ next: () => this.documents.update((items) => items.filter((item) => item.id !== document.id)), error: () => this.error.set('Could not delete document.') });
  }
}
