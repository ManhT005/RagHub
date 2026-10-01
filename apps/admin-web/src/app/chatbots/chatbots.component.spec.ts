import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { vi } from 'vitest';

import { ChatbotsComponent } from './chatbots.component';
import { RaghubApiService } from '../core/raghub-api.service';

describe('ChatbotsComponent', () => {
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
    fixture.detectChanges();

    const model = (fixture.nativeElement as HTMLElement).querySelector<HTMLInputElement>('input[name="geminiChatModel"]');
    expect(model?.value).toBe('gemini-3.5-flash-lite');
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

    expect(fixture.nativeElement.querySelectorAll('.provider-row')).toHaveLength(1);
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

    expect(fixture.nativeElement.querySelectorAll('.provider-row')).toHaveLength(1);
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
