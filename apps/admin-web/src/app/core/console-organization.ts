import { session } from "./api-auth.interceptor";
import type { Organization } from "./raghub-api.service";

/** Resolve the console scope once; pages do not expose a tenant switcher. */
export function consoleOrganization(organizations: readonly Organization[]) {
  return (
    organizations.find((item) => item.id === session.organizationId) ??
    organizations.find((item) => item.slug === "raghub") ??
    organizations[0]
  );
}
