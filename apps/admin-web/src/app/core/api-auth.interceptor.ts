import { HttpInterceptorFn } from '@angular/common/http';

const tokenKey = 'raghub.access-token';
const organizationKey = 'raghub.organization-id';

export const apiAuthInterceptor: HttpInterceptorFn = (request, next) => {
  const token = sessionStorage.getItem(tokenKey);
  const organizationId = sessionStorage.getItem(organizationKey);
  let headers = request.headers;

  if (token) headers = headers.set('Authorization', `Bearer ${token}`);
  if (organizationId) headers = headers.set('X-Organization-ID', organizationId);
  return next(request.clone({ headers, withCredentials: true }));
};

export const session = {
  get organizationId(): string | null {
    return sessionStorage.getItem(organizationKey);
  },
  set organizationId(value: string | null) {
    value ? sessionStorage.setItem(organizationKey, value) : sessionStorage.removeItem(organizationKey);
  },
  set accessToken(value: string | null) {
    value ? sessionStorage.setItem(tokenKey, value) : sessionStorage.removeItem(tokenKey);
  },
};
