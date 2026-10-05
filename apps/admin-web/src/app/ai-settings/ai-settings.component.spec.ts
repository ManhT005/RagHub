import { TestBed } from '@angular/core/testing';
import { of, Subject } from 'rxjs';
import { AiSettingsComponent } from './ai-settings.component';
import { RaghubApiService } from '../core/raghub-api.service';
import { session } from '../core/api-auth.interceptor';

describe('AI Settings', () => {
  beforeEach(() => { session.organizationId = null; });
  afterEach(() => { session.organizationId = null; });

  it('submits local embedding without a secret and blocks duplicate saves while pending', async () => {
    const pending = new Subject<object>();
    const createProvider = vi.fn((_organizationId: string, _payload: unknown) => pending);
    TestBed.configureTestingModule({imports: [AiSettingsComponent], providers: [{
      provide: RaghubApiService, useValue: {
        organizations: () => of([{id: 'install', role: 'ADMIN'}]), providers: () => of([]), createProvider,
      },
    }]});
    const fixture = TestBed.createComponent(AiSettingsComponent);
    fixture.detectChanges(); await fixture.whenStable();
    const form = fixture.nativeElement.querySelector('form') as HTMLFormElement;
    form.dispatchEvent(new Event('submit', {bubbles: true, cancelable: true}));
    fixture.detectChanges();
    expect(createProvider).toHaveBeenCalledWith('install', expect.objectContaining({
      provider_type: 'LOCAL_SENTENCE_TRANSFORMER', capability: 'EMBEDDING', dimension: 384,
    }));
    expect(createProvider.mock.calls[0][1]).not.toHaveProperty('secret');
    expect(fixture.nativeElement.querySelector('button[type=submit]').disabled).toBe(true);
    pending.next({}); pending.complete(); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('button[type=submit]').disabled).toBe(false);
  });

  it('shows success for the backend uppercase provider status', async () => {
    TestBed.configureTestingModule({imports: [AiSettingsComponent], providers: [{
      provide: RaghubApiService, useValue: {
        organizations: () => of([{id: 'install', role: 'ADMIN'}]),
        providers: () => of([{id: 'provider', name: 'Ollama', capability: 'CHAT', enabled: true, model: 'gemma3:1b'}]),
        testProvider: () => of({status: 'OK'}),
      },
    }]});
    const fixture = TestBed.createComponent(AiSettingsComponent);
    fixture.detectChanges(); await fixture.whenStable();
    (fixture.nativeElement.querySelector('article button') as HTMLButtonElement).click();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('[role=status]').textContent).toContain('kết nối thành công');
  });
});
