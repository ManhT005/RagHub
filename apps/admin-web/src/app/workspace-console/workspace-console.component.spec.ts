import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { RaghubApiService } from '../core/raghub-api.service';
import { WorkspaceConsoleComponent } from './workspace-console.component';

describe('WorkspaceConsoleComponent', () => {
  it('offers one workspace creation action when no workspace exists', async () => {
    await TestBed.configureTestingModule({
      imports: [WorkspaceConsoleComponent],
      providers: [
        provideRouter([]),
        {
          provide: RaghubApiService,
          useValue: {
            organizations: () => of([{ id: 'org-1', name: 'Demo', slug: 'demo', role: 'OWNER' }]),
            workspaces: () => of([]),
          },
        },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(WorkspaceConsoleComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Tạo workspace đầu tiên');
  });

  it('renders the next actions when a workspace is not ready for chat', async () => {
    await TestBed.configureTestingModule({
      imports: [WorkspaceConsoleComponent],
      providers: [
        provideRouter([]),
        {
          provide: RaghubApiService,
          useValue: {
            organizations: () => of([{ id: 'org-1', name: 'Demo', slug: 'demo', role: 'OWNER' }]),
            workspaces: () => of([{ id: 'workspace-1', name: 'Knowledge', slug: 'knowledge', organization_id: 'org-1' }]),
            providers: () => of([]),
            documents: () => of([]),
            chatbots: () => of([]),
          },
        },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(WorkspaceConsoleComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Thiết lập AI');
    expect(text).toContain('Tải tài liệu');
    expect(text).toContain('Xuất bản chatbot');
  });

  it('uses a safe mapped error and retry for a retryable failed document', async () => {
    await TestBed.configureTestingModule({
      imports: [WorkspaceConsoleComponent],
      providers: [
        provideRouter([]),
        {
          provide: RaghubApiService,
          useValue: {
            organizations: () => of([{ id: 'org-1', name: 'Demo', slug: 'demo', role: 'OWNER' }]),
            workspaces: () => of([{ id: 'workspace-1', name: 'Knowledge', slug: 'knowledge', organization_id: 'org-1' }]),
            providers: () => of([]),
            chatbots: () => of([]),
            documents: () => of([{
              id: 'document-1', name: 'handbook.pdf', status: 'FAILED', stage: 'FAILED',
              created_at: '2026-09-29T00:00:00Z', document_version_id: 'version-1', job_id: null,
              progress: 65, attempts: 1, error_code: 'INDEX_UNAVAILABLE',
              error_message: 'password=secret host=private.internal', retryable: true,
            }]),
          },
        },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(WorkspaceConsoleComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('tạm thời không khả dụng');
    expect(text).not.toContain('password=secret');
    expect(text).not.toContain('private.internal');
    expect(text).toContain('Thử lại');
  });

  it('explains that a draft chatbot must be published before chat', async () => {
    await TestBed.configureTestingModule({
      imports: [WorkspaceConsoleComponent],
      providers: [
        provideRouter([]),
        {
          provide: RaghubApiService,
          useValue: {
            organizations: () => of([{ id: 'org-1', name: 'Demo', slug: 'demo', role: 'OWNER' }]),
            workspaces: () => of([{ id: 'workspace-1', name: 'Knowledge', slug: 'knowledge', organization_id: 'org-1' }]),
            providers: () => of([]),
            documents: () => of([]),
            chatbots: () => of([{ id: 'bot-1', workspace_id: 'workspace-1', name: 'Assistant', system_prompt: '', model: null, retrieval_limit: 5, published: false, created_at: '', updated_at: null }]),
          },
        },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(WorkspaceConsoleComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Xuất bản chatbot');
    expect(fixture.nativeElement.querySelector('textarea')?.disabled).toBe(true);
  });

  it('selects a citation by id and falls back to document name', async () => {
    await TestBed.configureTestingModule({
      imports: [WorkspaceConsoleComponent],
      providers: [
        provideRouter([]),
        { provide: RaghubApiService, useValue: { organizations: () => of([]), workspaces: () => of([]) } },
      ],
    }).compileComponents();
    const fixture = TestBed.createComponent(WorkspaceConsoleComponent);
    const component = fixture.componentInstance as any;
    component.documents.set([
      { id: 'doc-1', name: 'handbook.pdf', status: 'READY' },
      { id: 'doc-2', name: 'policy.pdf', status: 'READY' },
    ]);

    component.selectCitation({ document_id: 'doc-2', document_name: 'handbook.pdf' });
    expect(component.selectedDocumentId()).toBe('doc-2');
    component.selectCitation({ document_name: 'handbook.pdf' });
    expect(component.selectedDocumentId()).toBe('doc-1');
  });
});
