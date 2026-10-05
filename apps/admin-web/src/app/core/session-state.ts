import { signal } from '@angular/core';
const tokenKey = 'raghub.access-token';
const organizationKey = 'raghub.organization-id';
export const organizationSelection = signal<string | null>(sessionStorage.getItem(organizationKey));
export const session = {
  get accessToken(): string | null { return sessionStorage.getItem(tokenKey); },
  set accessToken(value: string | null) {
    value ? sessionStorage.setItem(tokenKey, value) : sessionStorage.removeItem(tokenKey);
  },
  get organizationId(): string | null {
    organizationSelection();
    return sessionStorage.getItem(organizationKey);
  },
  set organizationId(value: string | null) {
    value ? sessionStorage.setItem(organizationKey, value) : sessionStorage.removeItem(organizationKey);
    organizationSelection.set(value);
  },
};
