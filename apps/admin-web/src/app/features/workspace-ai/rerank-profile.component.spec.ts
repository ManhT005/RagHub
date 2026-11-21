import { TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { of } from 'rxjs';
import { ProviderApiService } from '../../core/api/provider-api.service';
import { WorkspaceContextStore } from '../../core/workspace-context/workspace-context.store';
import { contextFixture, workspaceFixture } from '../selfhost-test-fixtures';
import { RerankProfileComponent } from './rerank-profile.component';

describe('Optional workspace rerank', () => {
  const api = { workspaceModels: vi.fn(), rerankBinding: vi.fn(), bindRerank: vi.fn(), prepareLocalRerank: vi.fn() };
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
      mode: 'provider', model_id: 'rerank-1', candidate_limit: 40, top_n: 8, timeout_seconds: 5,
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
  it('lets a workspace choose local reranking and explicitly turn it off', () => {
    api.rerankBinding.mockReturnValue(of({ mode: 'off', model_id: null,
      candidate_limit: 40, top_n: 8, timeout_seconds: 5,
      local: { ready: true, status: 'INSTALLED', model: 'multilingual-reranker' } }));
    const view = TestBed.createComponent(RerankProfileComponent);
    view.detectChanges();
    const select = view.nativeElement.querySelector('select') as HTMLSelectElement;
    select.value = '__local__';
    select.dispatchEvent(new Event('change'));
    view.detectChanges();
    view.componentInstance['save']();
    expect(api.bindRerank).toHaveBeenLastCalledWith('workspace-1', {
      mode: 'local', model_id: null, candidate_limit: 30, top_n: 5, timeout_seconds: 20,
    });
    view.componentInstance['selected'] = '';
    view.componentInstance['save']();
    expect(api.bindRerank).toHaveBeenLastCalledWith('workspace-1', expect.objectContaining({ mode: 'off' }));
  });
  it('blocks local selection until the model is installed and limits preparation to admins', () => {
    api.rerankBinding.mockReturnValue(of({ mode: 'off', model_id: null,
      candidate_limit: 12, top_n: 5, timeout_seconds: 10,
      local: { ready: false, status: 'AVAILABLE', can_prepare: false, download_enabled: true } }));
    const view = TestBed.createComponent(RerankProfileComponent);
    view.detectChanges();
    expect(view.nativeElement.querySelector('option[value="__local__"]').disabled).toBe(true);
    const component = view.componentInstance;
    component['selected'] = '__local__';
    component['save']();
    component['prepareLocal']();
    expect(api.bindRerank).not.toHaveBeenCalled();
    expect(api.prepareLocalRerank).not.toHaveBeenCalled();
  });
  it('queues an admin download and refreshes readiness without changing the chosen mode', async () => {
    const binding = { mode: 'off', model_id: null, candidate_limit: 12, top_n: 5, timeout_seconds: 10,
      local: { ready: false, status: 'AVAILABLE', can_prepare: true, download_enabled: true } };
    api.rerankBinding.mockReturnValueOnce(of(binding)).mockReturnValue(of({ ...binding,
      local: { ...binding.local, ready: true, status: 'INSTALLED' } }));
    api.prepareLocalRerank.mockReturnValue(of({ status: 'QUEUED' }));
    const view = TestBed.createComponent(RerankProfileComponent);
    view.detectChanges();
    const button = [...view.nativeElement.querySelectorAll('button')].find((item: HTMLButtonElement) => item.textContent?.includes('Tải model local')) as HTMLButtonElement;
    button.click();
    await new Promise(resolve => setTimeout(resolve, 30));
    view.detectChanges();
    expect(api.prepareLocalRerank).toHaveBeenCalledWith('workspace-1');
    expect(view.componentInstance['local']()?.ready).toBe(true);
    expect(view.componentInstance['selected']).toBe('');
    expect(api.bindRerank).not.toHaveBeenCalled();
    view.destroy();
  });
});
