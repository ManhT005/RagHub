import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { of } from 'rxjs';
import { WorkspaceApiService } from '../../core/api/workspace-api.service';
import { ProviderApiService } from '../../core/api/provider-api.service';
import { RaghubApiService } from '../../core/raghub-api.service';
import { session } from '../../core/api-auth.interceptor';
import { workspaceFixture } from '../selfhost-test-fixtures';
import { WorkspacesPageComponent } from './workspaces-page.component';
describe('Workspace aggregate list', () => {
  const api = { list: vi.fn(), create: vi.fn(), update: vi.fn(), changeEmbedding: vi.fn() };
  const providers = { models: vi.fn() }; const documents = vi.fn();
  beforeEach(async () => {
    vi.clearAllMocks(); session.organizationId = 'org-1';
    api.list.mockReturnValue(of(Array.from({ length: 12 }, (_, i) => ({ ...workspaceFixture, id: `workspace-${i}` }))));
    await TestBed.configureTestingModule({ imports: [WorkspacesPageComponent], providers: [provideRouter([]), provideNoopAnimations(), { provide: WorkspaceApiService, useValue: api }, { provide: ProviderApiService, useValue: providers }, { provide: RaghubApiService, useValue: { organizations: () => of([{ id: 'org-1', name: 'Organization', role: 'WORKSPACE_ADMIN' }]), documents } }] }).compileComponents();
  });
  afterEach(() => { session.organizationId = null; });
  it('uses one summary request regardless of workspace count', () => {
    const view = TestBed.createComponent(WorkspacesPageComponent); view.detectChanges();
    expect(api.list).toHaveBeenCalledTimes(1); expect(documents).not.toHaveBeenCalled(); expect(providers.models).not.toHaveBeenCalled();
    expect(view.nativeElement.textContent).toContain('current-model'); view.destroy();
  });
  it('hides system-only creation from a delegated member', () => {
    const view = TestBed.createComponent(WorkspacesPageComponent); view.detectChanges();
    expect(view.nativeElement.textContent).not.toContain('+ Tạo workspace'); view.destroy();
  });
});
