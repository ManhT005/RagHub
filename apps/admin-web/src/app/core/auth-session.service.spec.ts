import { HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { AuthSessionService } from './auth-session.service';
import { session } from './session-state';

describe('AuthSessionService', () => {
  let auth: AuthSessionService;
  let http: HttpTestingController;
  beforeEach(() => {
    sessionStorage.clear();
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    auth = TestBed.inject(AuthSessionService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());
  it('shares a single refresh among five subscribers and rotates again later', () => {
    const tokens: string[] = [];
    for (let i = 0; i < 5; i++) auth.refresh().subscribe(token => tokens.push(token));
    const request = http.expectOne('/api/v1/auth/refresh');
    expect(request.request.withCredentials).toBe(true);
    request.flush({ access_token: 'new' });
    expect(tokens).toEqual(['new', 'new', 'new', 'new', 'new']);
    auth.refresh().subscribe();
    http.expectOne('/api/v1/auth/refresh').flush({ access_token: 'newer' });
  });
  it('restores a new tab without an access token', () => {
    let restored = false;
    auth.restoreSession().subscribe(value => restored = value);
    http.expectOne('/api/v1/auth/refresh').flush({ access_token: 'restored' });
    expect(restored).toBe(true);
    expect(auth.accessToken()).toBe('restored');
  });
  it('clears session only on a definitive refresh 401', () => {
    auth.acceptToken('old'); session.organizationId = 'org';
    auth.refresh().subscribe({ error: () => undefined });
    http.expectOne('/api/v1/auth/refresh').flush({}, { status: 401, statusText: 'Unauthorized' });
    expect(auth.accessToken()).toBeNull();
    expect(session.organizationId).toBeNull();
    auth.restoreSession().subscribe(value => expect(value).toBe(false));
    http.expectNone('/api/v1/auth/refresh');
  });
  for (const status of [0, 500, 503]) {
    it(`preserves tokens on transient refresh ${status}`, () => {
      auth.acceptToken('old'); session.organizationId = 'org';
      auth.refresh().subscribe({ error: error => expect(error).toBeInstanceOf(HttpErrorResponse) });
      const request = http.expectOne('/api/v1/auth/refresh');
      if (status === 0) request.error(new ProgressEvent('error'));
      else request.flush({}, { status, statusText: 'Unavailable' });
      expect(auth.accessToken()).toBe('old');
      expect(session.organizationId).toBe('org');
    });
  }
  it('calls logout with cookies and clears locally when backend is unavailable', () => {
    auth.acceptToken('old'); session.organizationId = 'org';
    auth.logout().subscribe();
    expect(auth.accessToken()).toBeNull();
    const request = http.expectOne('/api/v1/auth/logout');
    expect(request.request.withCredentials).toBe(true);
    request.flush({}, { status: 503, statusText: 'Unavailable' });
  });
  it('does not restore a session after logout during refresh', () => {
    auth.refresh().subscribe({ error: () => undefined });
    auth.logout().subscribe();
    http.expectNone('/api/v1/auth/logout');
    http.expectOne('/api/v1/auth/refresh').flush({ access_token: 'stale' });
    http.expectOne('/api/v1/auth/logout').flush(null);
    expect(auth.accessToken()).toBeNull();
  });
});
