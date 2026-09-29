import { TestBed } from '@angular/core/testing';

import { AppComponent } from './app.component';
import { appConfig } from './app.config';

describe('AppComponent', () => {
  it('renders the RagHub brand', async () => {
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: appConfig.providers,
    }).compileComponents();

    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('RagHub');
  });

  it('marks the application shell with the dark design system', async () => {
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: appConfig.providers,
    }).compileComponents();

    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.app-shell')?.classList).toContain(
      'design-system-dark',
    );
  });

  it('links navigation to Workspace Console and organization settings', async () => {
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: appConfig.providers,
    }).compileComponents();

    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    const element: HTMLElement = fixture.nativeElement;
    expect(element.textContent).toContain('Cài đặt tổ chức');
    expect(element.querySelector('a[href="/workspaces"]')).not.toBeNull();
  });
});
