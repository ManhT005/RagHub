import { TestBed } from '@angular/core/testing';
import { Router, UrlTree, provideRouter } from '@angular/router';
import { firstValueFrom, of, throwError, Observable } from 'rxjs';
import { AuthSessionService } from '../core/auth-session.service';
import { SetupStateService } from './setup-state.service';
import { installationReady, setupAvailable } from './setup.guard';

describe('setup guards', () => {
  function configure(initialized: boolean, authenticated = false, unavailable = false) {
    const setup = { status: vi.fn(() => unavailable ? throwError(() => new Error('offline')) : of({ initialized })), invalidate: vi.fn() };
    TestBed.configureTestingModule({ providers: [provideRouter([]), { provide: SetupStateService, useValue: setup }, { provide: AuthSessionService, useValue: { restoreSession: () => of(authenticated) } }] });
    return setup;
  }
  const run = (guard: typeof installationReady) => firstValueFrom(TestBed.runInInjectionContext(() => guard({} as never, {} as never)) as Observable<boolean | UrlTree>);
  it('routes a fresh installation to setup before auth', async () => {
    configure(false);
    expect((await run(installationReady) as UrlTree).toString()).toBe('/setup');
    expect(await run(setupAvailable)).toBe(true);
  });
  it('allows existing installations into auth/protected guards', async () => {
    configure(true); expect(await run(installationReady)).toBe(true);
  });
  for (const authenticated of [true, false]) {
    it(`closes setup after initialization with authenticated=${authenticated}`, async () => {
      const setup = configure(true, authenticated);
      expect((await run(setupAvailable) as UrlTree).toString()).toBe(authenticated ? '/app/workspaces' : '/auth');
      expect(setup.invalidate).toHaveBeenCalled();
    });
  }
  it('cancels navigation on outage without a setup/login redirect', async () => {
    configure(false, false, true);
    expect(await run(installationReady)).toBe(false);
    expect(await run(setupAvailable)).toBe(false);
  });
});
