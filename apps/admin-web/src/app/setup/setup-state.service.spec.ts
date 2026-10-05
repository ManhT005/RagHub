import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { SetupStateService } from './setup-state.service';

describe('SetupStateService', () => {
  let setup: SetupStateService;
  let http: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    setup = TestBed.inject(SetupStateService); http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());
  it('shares status discovery, caches success, and supports an explicit recheck', () => {
    setup.status().subscribe(); setup.status().subscribe();
    http.expectOne('/api/v1/setup/status').flush({ status: 'UNINITIALIZED', initialized: false });
    setup.status().subscribe(status => expect(status.initialized).toBe(false));
    http.expectNone('/api/v1/setup/status');
    setup.invalidate(); setup.status().subscribe();
    http.expectOne('/api/v1/setup/status').flush({ status: 'INITIALIZED', initialized: true });
  });
  it('does not interpret an outage as a fresh installation', () => {
    setup.status().subscribe({ error: () => undefined });
    http.expectOne('/api/v1/setup/status').flush({}, { status: 503, statusText: 'Unavailable' });
    expect(setup.unavailable()).toBe(true);
    setup.status().subscribe();
    http.expectOne('/api/v1/setup/status').flush({ status: 'INITIALIZED', initialized: true });
    expect(setup.unavailable()).toBe(false);
  });
  it('shows dependency failures while leaving optional AI/email outside readiness', () => {
    setup.readiness().subscribe(checks => {
      expect(checks.find(check => check.name === 'redis')?.ready).toBe(false);
      expect(checks.find(check => check.name === 'postgres')?.ready).toBe(true);
      expect(checks).toHaveLength(5);
    });
    http.expectOne('/health/ready').flush({ error: { details: { dependencies: { redis: 'unavailable' } } } }, { status: 503, statusText: 'Unavailable' });
  });
});
