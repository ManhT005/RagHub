import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { DashboardComponent } from './dashboard.component';

describe('DashboardComponent', () => {
  it('guides the operator into Workspace Console', async () => {
    await TestBed.configureTestingModule({
      imports: [DashboardComponent],
      providers: [provideRouter([])],
    }).compileComponents();

    const fixture = TestBed.createComponent(DashboardComponent);
    fixture.detectChanges();

    const element: HTMLElement = fixture.nativeElement;
    expect(element.textContent).toContain('Mở Workspace Console');
    expect(element.querySelector('a[href="/workspaces"]')).not.toBeNull();
  });
});
