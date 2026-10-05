import { HttpInterceptorFn } from '@angular/common/http';
import { signal } from '@angular/core';

const tokenKey = 'raghub.access-token';
const organizationKey = 'raghub.organization-id';
export const organizationSelection = signal<string | null>(sessionStorage.getItem(organizationKey));

export const apiAuthInterceptor: HttpInterceptorFn = (request, next) => {
  const token = sessionStorage.getItem(tokenKey);
  const organizationId = sessionStorage.getItem(organizationKey);
  let headers = request.headers;

  if (token) headers = headers.set('Authorization', `Bearer ${token}`);
  if (organizationId) headers = headers.set('X-Organization-ID', organizationId);
  return next(request.clone({ headers, withCredentials: true }));
};

export const session = {
  get accessToken(): string | null {
    return sessionStorage.getItem(tokenKey);
  },
  get organizationId(): string | null {
    organizationSelection();
    return sessionStorage.getItem(organizationKey);
  },
  set organizationId(value: string | null) {
    value ? sessionStorage.setItem(organizationKey, value) : sessionStorage.removeItem(organizationKey);
    organizationSelection.set(value);
  },
  set accessToken(value: string | null) {
    value ? sessionStorage.setItem(tokenKey, value) : sessionStorage.removeItem(tokenKey);
  },
};
