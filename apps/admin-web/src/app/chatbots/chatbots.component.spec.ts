import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

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
});
