import { Location } from '@angular/common';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { AppComponent } from './app.component';
import { appConfig } from './app.config';
import { of } from 'rxjs';
import { AuthSessionService } from './core/auth-session.service';
import { SetupStateService } from './setup/setup-state.service';

let mockAccessToken: string | null = null;

const providers = [
  ...appConfig.providers, provideHttpClientTesting(),
  { provide: SetupStateService, useValue: { status: () => of({ initialized: true }), unavailable: signal(false) } },
  { provide: AuthSessionService, useValue: { restoreSession: () => of(!!mockAccessToken), accessToken: () => mockAccessToken, restoreError: signal(false) } },
];

describe('AppComponent', () => {
  it('redirects legacy documents without a workspace to the workspace selector', async () => {
    mockAccessToken = 'test-token';
    await TestBed.configureTestingModule({ providers }).compileComponents();
    const router = TestBed.inject(Router);
    const location = TestBed.inject(Location);
    await router.navigateByUrl('/documents');
    expect(location.path()).toBe('/app/workspaces');
  });

  it('redirects an unauthenticated profile visit to login', async () => {
    mockAccessToken = null;
    await TestBed.configureTestingModule({ providers }).compileComponents();
    const router = TestBed.inject(Router);
    const location = TestBed.inject(Location);
    await router.navigateByUrl('/app/profile');
    expect(location.path()).toContain('/auth');
  });

  it('hosts routed page content', async () => {
    await TestBed.configureTestingModule({ imports: [AppComponent], providers }).compileComponents();
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('router-outlet')).not.toBeNull();
  });
});
