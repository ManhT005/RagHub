import { TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { of } from 'rxjs';
import { ProviderApiService } from '../../core/api/provider-api.service';
import { WorkspaceContextStore } from '../../core/workspace-context/workspace-context.store';
import { contextFixture, workspaceFixture } from '../selfhost-test-fixtures';
import { RerankProfileComponent } from './rerank-profile.component';

describe('Optional workspace rerank', () => {
  const api = { workspaceModels: vi.fn(), rerankBinding: vi.fn(), bindRerank: vi.fn() };
  let context: ReturnType<typeof contextFixture>;
  beforeEach(async () => {
    vi.clearAllMocks();
    context = contextFixture(['workspace.view', 'workspace.edit', 'ai.view']);
    api.workspaceModels.mockReturnValue(of([{ id: 'rerank-1', enabled: true, connection_enabled: true,
      connection_status: 'CONNECTED', availability_status: 'AVAILABLE', model: 'rerank-3', provider_name: 'Voyage' },
    { id: 'unhealthy', enabled: true, connection_enabled: true, connection_status: 'ERROR', availability_status: 'AVAILABLE' }]));
    api.rerankBinding.mockReturnValue(of({ model_id: null, candidate_limit: 40, top_n: 8, timeout_seconds: 5 }));
    api.bindRerank.mockReturnValue(of({}));
    await TestBed.configureTestingModule({ imports: [RerankProfileComponent], providers: [
      provideNoopAnimations(), { provide: ProviderApiService, useValue: api },
      { provide: WorkspaceContextStore, useValue: context },
    ] }).compileComponents();
  });
  it('allows healthy rerank binding and explicit disable without reindex', () => {
    const view = TestBed.createComponent(RerankProfileComponent);
    view.detectChanges();
    const component = view.componentInstance;
    expect(component['models']()).toHaveLength(1);
    component['selected'] = 'rerank-1';
    component['save']();
    expect(api.bindRerank).toHaveBeenLastCalledWith('workspace-1', {
      model_id: 'rerank-1', candidate_limit: 40, top_n: 8, timeout_seconds: 5,
    });
    component['selected'] = '';
    component['save']();
    expect(api.bindRerank).toHaveBeenLastCalledWith('workspace-1', expect.objectContaining({ model_id: null }));
    expect(context.refresh).not.toHaveBeenCalled();
  });
  it('rejects invalid bounds, unavailable models and insufficient permissions', () => {
    const view = TestBed.createComponent(RerankProfileComponent);
    view.detectChanges();
    const component = view.componentInstance;
    component['selected'] = 'unhealthy';
    component['save']();
    component['selected'] = 'rerank-1'; component['topN'] = 41;
    component['save']();
    component['topN'] = 8;
    context.accessInfo.set({ workspace_id: 'workspace-1', is_system_admin: false, permissions: ['workspace.view'] });
    component['save']();
    expect(api.bindRerank).not.toHaveBeenCalled();
  });
  it('reloads rerank settings for the newly selected workspace', () => {
    const view = TestBed.createComponent(RerankProfileComponent);
    view.detectChanges();
    context.workspace.set({ ...workspaceFixture, id: 'workspace-2' });
    view.detectChanges();
    expect(api.workspaceModels).toHaveBeenLastCalledWith('workspace-2', 'RERANK');
    expect(api.rerankBinding).toHaveBeenLastCalledWith('workspace-2');
  });
});
