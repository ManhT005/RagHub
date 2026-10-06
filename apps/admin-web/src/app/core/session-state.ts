import { signal } from '@angular/core';
const organizationKey = 'raghub.organization-id';
let inMemoryAccessToken: string | null = null;
export const organizationSelection = signal<string | null>(sessionStorage.getItem(organizationKey));
export const session = {
  get accessToken(): string | null { return inMemoryAccessToken; },
  set accessToken(value: string | null) {
    inMemoryAccessToken = value;
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
