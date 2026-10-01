import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, Subject, throwError } from 'rxjs';
import { vi } from 'vitest';

import { ChatbotsComponent } from './chatbots.component';
import { RaghubApiService } from '../core/raghub-api.service';

describe('ChatbotsComponent', () => {
  async function wizard(testProvider: ReturnType<typeof vi.fn>, bindWorkspaceProviders = vi.fn(() => of({})), updateChatbot = vi.fn(() => of({ id: 'bot-1', published: true }))) {
    const base = { organization_id: 'org-1', enabled: true, name: 'Local', provider_type: 'OLLAMA', model: 'gemma3:1b' };
    await TestBed.configureTestingModule({
      imports: [ChatbotsComponent], providers: [provideRouter([]), { provide: RaghubApiService, useValue: {
        organizations: () => of([{ id: 'org-1', name: 'Demo' }]),
        workspaces: () => of([{ id: 'workspace-1', name: 'Knowledge' }]),
        providers: () => of([{ ...base, id: 'embedding-1', capability: 'EMBEDDING' }, { ...base, id: 'chat-1', capability: 'CHAT' }]),
        chatbots: () => of([{ id: 'bot-1', name: 'Bot', system_prompt: '', retrieval_limit: 5, published: true }]),
        testProvider, bindWorkspaceProviders, updateChatbot,
      }}],
    }).compileComponents();
    const fixture = TestBed.createComponent(ChatbotsComponent);
    fixture.detectChanges();
    return fixture;
  }

  it('keeps later stages hidden when either AI connection fails', async () => {
    const bind = vi.fn(() => of({}));
    const fixture = await wizard(vi.fn((id: string) => id === 'chat-1' ? throwError(() => new Error('offline')) : of({ status: 'OK' })), bind);
    const component = fixture.componentInstance as any;
    component.continueConnection();
    fixture.detectChanges();
    expect(component.currentStep()).toBe(1);
    expect(bind).not.toHaveBeenCalled();
    expect(fixture.nativeElement.querySelectorAll('.workflow-grid > article:not([hidden])')).toHaveLength(1);
    fixture.destroy();
  });

  it('advances only after both checks and workspace binding complete', async () => {
    const pending = new Subject<any>();
    const bind = vi.fn(() => pending);
    const fixture = await wizard(vi.fn(() => of({ status: 'OK' })), bind as any);
    const component = fixture.componentInstance as any;
    component.continueConnection();
    expect(component.currentStep()).toBe(1);
    expect(component.connectionBusy()).toBe(true);
    pending.next({}); pending.complete();
    fixture.detectChanges();
    expect(component.currentStep()).toBe(2);
    expect(bind).toHaveBeenCalledWith('workspace-1', 'embedding-1', 'chat-1');
    expect(fixture.nativeElement.querySelectorAll('.workflow-grid > article:not([hidden])')).toHaveLength(1);
    fixture.destroy();
  });

  it('keeps chat locked on publication failure and opens it after success', async () => {
    const update = vi.fn().mockReturnValueOnce(throwError(() => new Error('save failed'))).mockReturnValueOnce(of({ id: 'bot-1', published: true }));
    const fixture = await wizard(vi.fn(() => of({ status: 'OK' })), undefined, update);
    const component = fixture.componentInstance as any;
    component.continueBot();
    expect(update).not.toHaveBeenCalled();
    component.continueConnection();
    component.continueBot();
    expect(component.currentStep()).toBe(2);
    component.continueBot();
    fixture.detectChanges();
    expect(component.currentStep()).toBe(3);
    expect(fixture.nativeElement.querySelectorAll('.workflow-grid > article:not([hidden])')).toHaveLength(1);
    component.changeWorkspace();
    expect(component.currentStep()).toBe(1);
    fixture.destroy();
  });

  it('tells the user to create a workspace before configuring a chatbot', async () => {
    await TestBed.configureTestingModule({
      imports: [ChatbotsComponent],
      providers: [provideRouter([]), { provide: RaghubApiService, useValue: {
        organizations: () => of([{ id: 'org-1', name: 'Demo', slug: 'demo', role: 'OWNER' }]),
        workspaces: () => of([]), providers: () => of([]),
      } }],
    }).compileComponents();

    const fixture = TestBed.createComponent(ChatbotsComponent);
    fixture.detectChanges();

    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Tạo không gian làm việc');
    fixture.destroy();
  });

  it('defaults Gemini setup to the configured Flash Lite chat model', async () => {
    await TestBed.configureTestingModule({
      imports: [ChatbotsComponent],
      providers: [provideRouter([]), { provide: RaghubApiService, useValue: {
        organizations: () => of([{ id: 'org-1', name: 'Demo', slug: 'demo', role: 'OWNER' }]),
        workspaces: () => of([{ id: 'workspace-1', name: 'Knowledge', slug: 'knowledge', organization_id: 'org-1' }]),
        providers: () => of([]), chatbots: () => of([]),
      } }],
    }).compileComponents();

    const fixture = TestBed.createComponent(ChatbotsComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    (fixture.componentInstance as any).showGeminiForm = true;
    fixture.detectChanges();

    expect((fixture.componentInstance as any).geminiChatModel).toBe('gemini-3.5-flash-lite');
    fixture.destroy();
  });

  it('shows backend providers in separate embedding and chat selectors', async () => {
    const local = { organization_id: 'org-1', enabled: true, base_url: null, dimension: null, config_json: {}, has_secret: false, created_at: '', updated_at: null };
    await TestBed.configureTestingModule({
      imports: [ChatbotsComponent], providers: [provideRouter([]), { provide: RaghubApiService, useValue: {
        organizations: () => of([{ id: 'org-1', name: 'Demo', slug: 'demo', role: 'OWNER' }]),
        workspaces: () => of([{ id: 'workspace-1', name: 'Knowledge', slug: 'knowledge', organization_id: 'org-1' }]),
        providers: () => of([
          { ...local, id: 'embed-1', name: 'Embedding local', provider_type: 'LOCAL_SENTENCE_TRANSFORMER', capability: 'EMBEDDING', model: 'multilingual-mini', dimension: 384 },
          { ...local, id: 'chat-1', name: 'Chat Ollama', provider_type: 'OLLAMA', capability: 'CHAT', model: 'gemma3:1b' },
        ]), chatbots: () => of([]),
      }}],
    }).compileComponents();
    const fixture = TestBed.createComponent(ChatbotsComponent);
    fixture.detectChanges(); await fixture.whenStable(); fixture.detectChanges();
    expect((fixture.nativeElement.querySelector('select[name="embeddingProvider"]') as HTMLSelectElement | null)?.value).toBe('embed-1');
    expect((fixture.nativeElement.querySelector('select[name="chatProvider"]') as HTMLSelectElement | null)?.value).toBe('chat-1');
    expect(fixture.nativeElement.textContent).toContain('multilingual-mini');
    expect(fixture.nativeElement.textContent).toContain('gemma3:1b');
    fixture.destroy();
  });

  it('creates the configured Gemini embedding model', async () => {
    const payloads: Array<{ model: string; capability: string }> = [];
    await TestBed.configureTestingModule({
      imports: [ChatbotsComponent],
      providers: [provideRouter([]), { provide: RaghubApiService, useValue: {
        organizations: () => of([{ id: 'org-1', name: 'Demo', slug: 'demo', role: 'OWNER' }]),
        workspaces: () => of([{ id: 'workspace-1', name: 'Knowledge', slug: 'knowledge', organization_id: 'org-1' }]),
        providers: () => of([]), chatbots: () => of([]),
        createProvider: (_organizationId: string, payload: { model: string; capability: string }) => {
          payloads.push(payload);
          return of({ id: payload.capability === 'EMBEDDING' ? 'embedding-1' : 'chat-1' });
        },
        bindWorkspaceProviders: () => of({}),
      } }],
    }).compileComponents();

    const fixture = TestBed.createComponent(ChatbotsComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    (fixture.componentInstance as any).geminiApiKey = 'test-key';
    (fixture.componentInstance as any).configureGemini();

    expect(payloads.find((payload) => payload.capability === 'EMBEDDING')?.model).toBe('gemini-embedding-2');
    fixture.destroy();
  });

  it('links a selected chatbot to its settings page', async () => {
    await TestBed.configureTestingModule({
      imports: [ChatbotsComponent], providers: [provideRouter([]), { provide: RaghubApiService, useValue: {
        organizations: () => of([{ id: 'org-1', name: 'Demo', slug: 'demo', role: 'OWNER' }]),
        workspaces: () => of([{ id: 'workspace-1', name: 'Knowledge', slug: 'knowledge', organization_id: 'org-1' }]),
        providers: () => of([]), chatbots: () => of([{ id: 'bot-1', workspace_id: 'workspace-1', name: 'Bot', system_prompt: '', model: null, retrieval_limit: 5, published: true, created_at: '', updated_at: null }]),
      }}],
    }).compileComponents();
    const fixture = TestBed.createComponent(ChatbotsComponent);
    fixture.detectChanges(); await fixture.whenStable(); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('a[href="/app/chatbots/bot-1/settings"]')).not.toBeNull();
  });

  it('shows one row when duplicate provider configurations exist', async () => {
    const provider = {
      organization_id: 'org-1', name: 'Chat Gemini', provider_type: 'GOOGLE_GEMINI' as const,
      capability: 'CHAT' as const, base_url: null, model: 'gemini-3.5-flash-lite', dimension: null,
      config_json: {}, enabled: true, has_secret: true, created_at: '', updated_at: null,
    };
    await TestBed.configureTestingModule({
      imports: [ChatbotsComponent], providers: [provideRouter([]), { provide: RaghubApiService, useValue: {
        organizations: () => of([{ id: 'org-1', name: 'Demo', slug: 'demo', role: 'OWNER' }]),
        workspaces: () => of([{ id: 'workspace-1', name: 'Knowledge', slug: 'knowledge', organization_id: 'org-1' }]),
        providers: () => of([{ ...provider, id: 'chat-1' }, { ...provider, id: 'chat-2' }]), chatbots: () => of([]),
      } }],
    }).compileComponents();

    const fixture = TestBed.createComponent(ChatbotsComponent);
    fixture.detectChanges(); await fixture.whenStable(); fixture.detectChanges();

    expect(fixture.nativeElement.querySelectorAll('select[name="chatProvider"] option')).toHaveLength(2);
    fixture.destroy();
  });

  it('does not show disabled providers in the advanced configuration list', async () => {
    const provider = {
      organization_id: 'org-1', name: 'Embedding Gemini', provider_type: 'GOOGLE_GEMINI' as const,
      capability: 'EMBEDDING' as const, base_url: null, dimension: 3072,
      config_json: {}, has_secret: true, created_at: '', updated_at: null,
    };
    await TestBed.configureTestingModule({
      imports: [ChatbotsComponent], providers: [provideRouter([]), { provide: RaghubApiService, useValue: {
        organizations: () => of([{ id: 'org-1', name: 'Demo', slug: 'demo', role: 'OWNER' }]),
        workspaces: () => of([{ id: 'workspace-1', name: 'Knowledge', slug: 'knowledge', organization_id: 'org-1' }]),
        providers: () => of([
          { ...provider, id: 'enabled-1', model: 'gemini-embedding-2', enabled: true },
          { ...provider, id: 'disabled-1', model: 'legacy-gemini', enabled: false },
        ]), chatbots: () => of([]),
      } }],
    }).compileComponents();
    const fixture = TestBed.createComponent(ChatbotsComponent);
    fixture.detectChanges(); await fixture.whenStable(); fixture.detectChanges();

    expect(fixture.nativeElement.querySelectorAll('select[name="embeddingProvider"] option')).toHaveLength(2);
    fixture.destroy();
  });

  it('re-encrypts existing Gemini provider credentials when saving a new API key', async () => {
    const updateProvider = vi.fn((id: string) => of({ id }));
    const provider = { organization_id: 'org-1', name: 'Gemini', provider_type: 'GOOGLE_GEMINI' as const,
      base_url: null, dimension: null, config_json: {}, enabled: true, has_secret: true, created_at: '', updated_at: null };
    await TestBed.configureTestingModule({
      imports: [ChatbotsComponent], providers: [provideRouter([]), { provide: RaghubApiService, useValue: {
        organizations: () => of([{ id: 'org-1', name: 'Demo', slug: 'demo', role: 'OWNER' }]),
        workspaces: () => of([{ id: 'workspace-1', name: 'Knowledge', slug: 'knowledge', organization_id: 'org-1' }]),
        providers: () => of([
          { ...provider, id: 'embedding-1', capability: 'EMBEDDING', model: 'gemini-embedding-2' },
          { ...provider, id: 'chat-1', capability: 'CHAT', model: 'gemini-3.5-flash-lite' },
        ]),
        chatbots: () => of([]), updateProvider, createProvider: vi.fn(), bindWorkspaceProviders: () => of({}),
      } }],
    }).compileComponents();
    const fixture = TestBed.createComponent(ChatbotsComponent);
    fixture.detectChanges(); await fixture.whenStable(); fixture.detectChanges();

    (fixture.componentInstance as any).geminiApiKey = 'new-test-key';
    (fixture.componentInstance as any).configureGemini();

    expect(updateProvider).toHaveBeenCalledWith('embedding-1', { secret: 'new-test-key' });
    expect(updateProvider).toHaveBeenCalledWith('chat-1', { secret: 'new-test-key' });
    fixture.destroy();
  });
});
