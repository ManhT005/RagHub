import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { RaghubApiService } from '../core/raghub-api.service';
import { DocumentsComponent } from './documents.component';

describe('DocumentsComponent ingestion errors', () => {
  for (const retryable of [false, true]) {
    it(`shows safe errors and retry availability ${retryable}`, async () => {
      await TestBed.configureTestingModule({
        imports: [DocumentsComponent],
        providers: [{ provide: RaghubApiService, useValue: {
          workspaces: () => of([{ id: 'workspace', name: 'Workspace' }]),
          documents: () => of([{
            id: 'document', name: 'test.pdf', status: 'FAILED', stage: 'FAILED',
            created_at: '2026-09-22T00:00:00Z', document_version_id: 'version',
            error_code: retryable ? 'INDEX_UNAVAILABLE' : 'INVALID_PDF',
            error_message: 'password=secret host=private.internal', retryable,
          }]),
        } }],
      }).compileComponents();
      const fixture = TestBed.createComponent(DocumentsComponent);
      fixture.detectChanges();
      const element: HTMLElement = fixture.nativeElement;
      expect(element.textContent).not.toContain('private.internal');
      expect(element.textContent).not.toContain('password=secret');
      expect(element.textContent).toContain(retryable ? 'temporarily unavailable' : 'Upload a valid PDF');
      const buttons = Array.from(element.querySelectorAll('button'));
      expect(buttons.some(button => button.textContent?.trim() === 'Retry')).toBe(retryable);
      fixture.destroy();
    });
  }
});
