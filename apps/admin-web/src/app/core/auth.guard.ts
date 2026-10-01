import { inject } from '@angular/core';
import { CanActivateChildFn, CanActivateFn, Router } from '@angular/router';

import { session } from './api-auth.interceptor';

const redirectToLogin = (url: string) => inject(Router).createUrlTree(['/auth'], { queryParams: { returnUrl: url } });

export const authenticated: CanActivateFn = (_route, state) =>
  session.accessToken ? true : redirectToLogin(state.url);

export const authenticatedChild: CanActivateChildFn = (_route, state) =>
  session.accessToken ? true : redirectToLogin(state.url);
