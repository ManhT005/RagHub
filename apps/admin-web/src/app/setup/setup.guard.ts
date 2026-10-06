import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of, switchMap } from 'rxjs';
import { AuthSessionService } from '../core/auth-session.service';
import { SetupStateService } from './setup-state.service';

export const installationReady: CanActivateFn = () => {
  const setup = inject(SetupStateService);
  const router = inject(Router);
  return setup.status().pipe(
    map(status => status.initialized || router.createUrlTree(['/setup'])),
    catchError(() => of(false)),
  );
};

export const setupAvailable: CanActivateFn = () => {
  const setup = inject(SetupStateService);
  const auth = inject(AuthSessionService);
  const router = inject(Router);
  // Recheck on each visit: another browser or the CLI may have completed setup.
  setup.invalidate();
  return setup.status().pipe(
    switchMap(status => status.initialized
      ? auth.restoreSession().pipe(map(restored => router.createUrlTree([restored ? '/app/workspaces' : '/auth'])))
      : of(true)),
    catchError(() => of(false)),
  );
};
