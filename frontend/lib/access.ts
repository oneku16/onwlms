import type { Role, SessionView } from "@/lib/api/session";

export interface AccessRule {
  readonly roles?: readonly Role[];
  readonly permissions?: readonly string[];
  readonly entitlements?: readonly string[];
  readonly requiresOrganization?: boolean;
}

function intersects(
  actual: readonly string[],
  required: readonly string[],
): boolean {
  return required.some((value) => actual.includes(value));
}

export function canAccess(
  session: SessionView,
  rule: AccessRule | undefined,
): boolean {
  if (!session.authenticated) {
    return false;
  }
  if (!rule) {
    return true;
  }
  if (rule.requiresOrganization && !session.activeOrganization) {
    return false;
  }
  if (rule.roles && !intersects(session.roles, rule.roles)) {
    return false;
  }
  if (rule.permissions && !intersects(session.permissions, rule.permissions)) {
    return false;
  }
  if (
    rule.entitlements &&
    !rule.entitlements.every((entitlement) =>
      session.entitlements.includes(entitlement),
    )
  ) {
    return false;
  }
  return true;
}
