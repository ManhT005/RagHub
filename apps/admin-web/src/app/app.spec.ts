import { TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { RouterLinkActive } from '@angular/router';

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

  it('uses the supplied RagHub logo in the sidebar brand', async () => {
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: appConfig.providers,
    }).compileComponents();

    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    const logo = fixture.nativeElement.querySelector('img.brand-logo') as HTMLImageElement;
    expect(logo?.getAttribute('src')).toBe('assets/logo.png');
    expect(logo?.getAttribute('alt')).toBe('RagHub');
  });

  it('keeps the application chrome free of redundant knowledge-space labels', async () => {
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: appConfig.providers,
    }).compileComponents();

    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.brand small')).toBeNull();
    expect(fixture.nativeElement.querySelector('nz-header .header-title strong')).toBeNull();
  });

  it('marks the application shell with the light monochrome design system', async () => {
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: appConfig.providers,
    }).compileComponents();

    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    const shell = fixture.nativeElement.querySelector('.app-shell') as HTMLElement;
    expect(shell.classList.contains('design-system-light')).toBe(true);
    expect(shell.classList.contains('design-system-dark')).toBe(false);
  });

  it('uses the light menu theme for the white sidebar', async () => {
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: appConfig.providers,
    }).compileComponents();

    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('ul')?.getAttribute('nztheme')).toBe('light');
  });

  it('groups the header label and page title for compact alignment', async () => {
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: appConfig.providers,
    }).compileComponents();

    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('nz-header .header-title')).not.toBeNull();
  });

  it('matches Overview only on the exact root route', async () => {
    await TestBed.configureTestingModule({
      imports: [AppComponent],
      providers: appConfig.providers,
    }).compileComponents();

    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();

    const overviewItem = fixture.debugElement.queryAll(By.directive(RouterLinkActive)).find((item) =>
      item.nativeElement.querySelector('a[href="/"]'),
    );
    const options = overviewItem?.injector.get(RouterLinkActive).routerLinkActiveOptions;
    expect(options).toEqual({ exact: true });
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
