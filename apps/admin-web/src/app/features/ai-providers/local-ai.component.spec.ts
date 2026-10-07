import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { of } from 'rxjs';
import { ProviderApiService, LocalAiModel } from '../../core/api/provider-api.service';
import { RaghubApiService } from '../../core/raghub-api.service';
import { LocalAiComponent } from './local-ai.component';

describe('Local AI download scaffold', () => {
  const model: LocalAiModel = { id: 'minilm-l6', repo: 'sentence-transformers/all-MiniLM-L6-v2',
    revision: 'fixed-revision', dimension: 384, languages: 'English', approximate_bytes: 91_000_000,
    docs_url: 'https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2',
    status: 'AVAILABLE', completed_bytes: 0, total_bytes: 0, error_code: null };
  const api = { localModels: vi.fn(), downloadLocal: vi.fn() };
  beforeEach(async () => {
    vi.clearAllMocks();
    api.localModels.mockReturnValue(of([model]));
    api.downloadLocal.mockReturnValue(of({ status: 'QUEUED' }));
    await TestBed.configureTestingModule({ imports: [LocalAiComponent], providers: [
      provideNoopAnimations(), provideRouter([]), { provide: ProviderApiService, useValue: api },
      { provide: RaghubApiService, useValue: { organizations: () => of([{ id: 'local-org', slug: 'raghub' }]) } },
    ] }).compileComponents();
  });
  afterEach(() => vi.useRealTimers());
  it('polls download progress until installed and uses the organization scope', () => {
    vi.useFakeTimers();
    api.localModels.mockReturnValueOnce(of([model]))
      .mockReturnValueOnce(of([{ ...model, status: 'DOWNLOADING', completed_bytes: 40, total_bytes: 100 }]))
      .mockReturnValueOnce(of([{ ...model, status: 'INSTALLED', completed_bytes: 100, total_bytes: 100 }]));
    const view = TestBed.createComponent(LocalAiComponent);
    view.detectChanges(); vi.advanceTimersByTime(0); view.detectChanges();
    expect(view.nativeElement.querySelector('a[href="https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2"][nz-button]')).not.toBeNull();
    view.componentInstance['download'](model);
    vi.advanceTimersByTime(0); vi.advanceTimersByTime(2000); vi.advanceTimersByTime(10_000);
    expect(api.downloadLocal).toHaveBeenCalledWith('local-org', 'minilm-l6');
    expect(api.localModels).toHaveBeenCalledTimes(3);
    expect(view.componentInstance['models']()[0].status).toBe('INSTALLED');
  });
  it('does not queue another model while a download is active', () => {
    vi.useFakeTimers();
    api.localModels.mockReturnValue(of([{ ...model, status: 'QUEUED' }]));
    const view = TestBed.createComponent(LocalAiComponent);
    view.detectChanges(); vi.advanceTimersByTime(0); view.detectChanges();
    expect(view.nativeElement.querySelector('a[href="https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2"][nz-button]')).not.toBeNull();
    view.componentInstance['download'](model);
    expect(api.downloadLocal).not.toHaveBeenCalled();
    view.destroy(); vi.advanceTimersByTime(10_000);
    expect(api.localModels).toHaveBeenCalledTimes(1);
  });
});
