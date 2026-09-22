import { ChangeDetectionStrategy, Component, ElementRef, inject, signal, viewChild } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { RaghubApiService, DocumentItem, Workspace } from '../core/raghub-api.service';

@Component({
  selector: 'raghub-documents',
  imports: [DatePipe, FormsModule],
  templateUrl: './documents.component.html',
  styleUrl: './documents.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DocumentsComponent {
  protected readonly workspaces = signal<Workspace[]>([]);
  protected readonly documents = signal<DocumentItem[]>([]);
  protected readonly error = signal('');
  protected workspaceId = '';
  protected readonly fileInput = viewChild<ElementRef<HTMLInputElement>>('fileInput');
  private readonly api = inject(RaghubApiService);

  constructor() { this.api.workspaces().subscribe({ next: (items) => { this.workspaces.set(items); this.workspaceId = items[0]?.id ?? ''; this.load(); }, error: () => this.error.set('Select an organization and sign in first.') }); }

  protected load(): void {
    if (!this.workspaceId) return;
    this.api.documents(this.workspaceId).subscribe({ next: (items) => this.documents.set(items), error: () => this.error.set('Could not load documents.') });
  }
  protected upload(): void {
    const file = this.fileInput()?.nativeElement.files?.[0];
    if (!file || !this.workspaceId) return;
    this.api.upload(this.workspaceId, file).subscribe({ next: () => this.load(), error: () => this.error.set('Upload failed. Only PDF is supported.') });
  }
  protected remove(document: DocumentItem): void {
    this.api.deleteDocument(this.workspaceId, document.id).subscribe({ next: () => this.documents.update((items) => items.filter((item) => item.id !== document.id)), error: () => this.error.set('Could not delete document.') });
  }
}
