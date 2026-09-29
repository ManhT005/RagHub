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
});
