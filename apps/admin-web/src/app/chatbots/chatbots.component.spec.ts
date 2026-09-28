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
});
