import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { apiAuthInterceptor, session } from './api-auth.interceptor';

describe('apiAuthInterceptor', () => {
  let client: HttpClient;
  let http: HttpTestingController;
  beforeEach(() => {
    sessionStorage.clear(); session.accessToken = 'expired';
    TestBed.configureTestingModule({ providers: [provideHttpClient(withInterceptors([apiAuthInterceptor])), provideHttpClientTesting(), provideRouter([])] });
    client = TestBed.inject(HttpClient); http = TestBed.inject(HttpTestingController);
    vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
  });
  afterEach(() => http.verify());
  it('retries five concurrent 401s through exactly one refresh', () => {
    for (let i = 0; i < 5; i++) client.get('/api/v1/workspaces').subscribe();
    const original = http.match('/api/v1/workspaces');
    original.forEach(request => request.flush({}, { status: 401, statusText: 'Unauthorized' }));
    http.expectOne('/api/v1/auth/refresh').flush({ access_token: 'new' });
    const retries = http.match('/api/v1/workspaces');
    expect(retries.length).toBe(5);
    retries.forEach(request => {
      expect(request.request.headers.get('Authorization')).toBe('Bearer new');
      request.flush([]);
    });
  });
  it('uses the new token for a delayed 401 without a second refresh', () => {
    client.get('/api/v1/a').subscribe(); client.get('/api/v1/b').subscribe();
    const a = http.expectOne('/api/v1/a'); const b = http.expectOne('/api/v1/b');
    a.flush({}, { status: 401, statusText: 'Unauthorized' });
    http.expectOne('/api/v1/auth/refresh').flush({ access_token: 'new' });
    http.expectOne('/api/v1/a').flush({});
    b.flush({}, { status: 401, statusText: 'Unauthorized' });
    http.expectNone('/api/v1/auth/refresh');
    http.expectOne('/api/v1/b').flush({});
  });
  it('redirects on refresh 401, but retains tokens on refresh 500', () => {
    client.get('/api/v1/me').subscribe({ error: () => undefined });
    http.expectOne('/api/v1/me').flush({}, { status: 401, statusText: 'Unauthorized' });
    http.expectOne('/api/v1/auth/refresh').flush({}, { status: 500, statusText: 'Unavailable' });
    expect(session.accessToken).toBe('expired');
    expect(TestBed.inject(Router).navigate).not.toHaveBeenCalled();
    client.get('/api/v1/me').subscribe({ error: () => undefined });
    http.expectOne('/api/v1/me').flush({}, { status: 401, statusText: 'Unauthorized' });
    http.expectOne('/api/v1/auth/refresh').flush({}, { status: 401, statusText: 'Unauthorized' });
    expect(session.accessToken).toBeNull();
    expect(TestBed.inject(Router).navigate).toHaveBeenCalled();
  });
  for (const path of ['/api/v1/auth/login', '/api/v1/auth/refresh', '/api/v1/auth/logout', '/api/v1/public/chatbots/x', '/api/v1/setup/initialize']) {
    it(`does not refresh a public/auth endpoint ${path}`, () => {
      client.post(path, {}).subscribe({ error: () => undefined });
      http.expectOne(path).flush({}, { status: 401, statusText: 'Unauthorized' });
      http.expectNone('/api/v1/auth/refresh');
    });
  }
  it('does not send bearer tokens to another origin', () => {
    client.get('https://example.com/api/v1/test').subscribe();
    const request = http.expectOne('https://example.com/api/v1/test');
    expect(request.request.headers.has('Authorization')).toBe(false);
    request.flush({});
  });
});
