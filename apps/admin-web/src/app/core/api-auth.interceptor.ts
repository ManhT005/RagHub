import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, of, switchMap, throwError } from 'rxjs';
import { AuthSessionService } from './auth-session.service';
import { session } from './session-state';
export { session, organizationSelection } from './session-state';
export const apiAuthInterceptor: HttpInterceptorFn = (request, next) => {
  const path = new URL(request.url, window.location.origin);
  if (path.origin !== window.location.origin || !path.pathname.startsWith('/api/v1/')) return next(request);
  const auth = inject(AuthSessionService);
  const router = inject(Router);
  const token = auth.accessToken();
  const authorize = (accessToken: string | null) => {
    let headers = request.headers;
    if (accessToken) headers = headers.set('Authorization', `Bearer ${accessToken}`);
    if (session.organizationId) headers = headers.set('X-Organization-ID', session.organizationId);
    return request.clone({ headers, withCredentials: true });
  };
  const publicEndpoint = /^\/api\/v1\/(?:auth\/(?:login|refresh|logout|password\/(?:forgot|reset))|public(?:\/|$)|setup(?:\/|$))/.test(path.pathname);
  return next(authorize(token)).pipe(catchError(error => {
    if (!(error instanceof HttpErrorResponse) || error.status !== 401 || publicEndpoint) return throwError(() => error);
    const refreshed = auth.accessToken();
    return (refreshed && refreshed !== token ? of(refreshed) : auth.refresh()).pipe(
      catchError(refreshError => {
        if (refreshError instanceof HttpErrorResponse && refreshError.status === 401) {
          auth.clearLocalSession();
          void router.navigate(['/auth'], { queryParams: { returnUrl: router.url } });
        }
        return throwError(() => refreshError);
      }),
      switchMap(accessToken => next(authorize(accessToken))),
    );
  }));
};
