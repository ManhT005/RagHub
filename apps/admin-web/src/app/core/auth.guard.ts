import { inject } from '@angular/core';
import { CanActivateChildFn, CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';
import { AuthSessionService } from './auth-session.service';
const checkSession = (url: string) => {
  const auth = inject(AuthSessionService);
  const router = inject(Router);
  return auth.restoreSession().pipe(
    map(authenticated => authenticated || router.createUrlTree(['/auth'], { queryParams: { returnUrl: url } })),
    catchError(() => of(false)),
  );
};
export const authenticated: CanActivateFn = (_route, state) => checkSession(state.url);
export const authenticatedChild: CanActivateChildFn = (_route, state) => checkSession(state.url);
