import "server-only";

import { cache } from "react";
import { cookies } from "next/headers";

import { ApiError } from "@/lib/api/errors";
import { activeOrganizationCookieName } from "@/lib/api/cookies";
import {
  anonymousSession,
  composeSession,
  parseCurrentIdentity,
  parseEntitlement,
  parseMembershipDiscoveries,
  parseOrganization,
  type MembershipView,
  type OrganizationView,
  type SessionView,
} from "@/lib/api/session";
import { serverApiRequest } from "@/lib/api/server";

const entitlementFeatures = [
  "academic",
  "moodle_integration",
  "ownid_sso",
  "timetable_generation",
] as const;

function fallbackOrganization(organizationId: string): OrganizationView {
  return {
    id: organizationId,
    displayName: `Organization ${organizationId.slice(0, 8)}`,
    locale: "en",
    timezone: "UTC",
    branding: {
      primaryColor: "#173f5f",
      accentColor: "#f0a43c",
    },
  };
}

async function loadMemberships(): Promise<readonly MembershipView[]> {
  const discoveries = await serverApiRequest(
    "/api/v1/auth/memberships",
    parseMembershipDiscoveries,
  );
  return Promise.all(
    discoveries.map(async (membership) => {
      let organization: OrganizationView;
      try {
        organization = await serverApiRequest(
          "/api/v1/organization",
          parseOrganization,
          { organizationId: membership.organizationId },
        );
      } catch (error) {
        if (error instanceof ApiError && error.status < 500) {
          throw error;
        }
        organization = fallbackOrganization(membership.organizationId);
      }
      return { ...membership, organization };
    }),
  );
}

async function loadEntitlements(
  organizationId: string | undefined,
): Promise<readonly string[]> {
  if (!organizationId) {
    return [];
  }
  const resolutions = await Promise.allSettled(
    entitlementFeatures.map((feature) =>
      serverApiRequest(`/api/v1/entitlements/${feature}`, parseEntitlement, {
        organizationId,
      }),
    ),
  );
  return resolutions.flatMap((resolution) =>
    resolution.status === "fulfilled" && resolution.value
      ? [resolution.value]
      : [],
  );
}

export const getSession = cache(async (): Promise<SessionView> => {
  try {
    const identity = await serverApiRequest(
      "/api/v1/auth/me",
      parseCurrentIdentity,
    );
    const memberships = await loadMemberships();
    const cookieStore = await cookies();
    const requestedOrganizationId = cookieStore.get(
      activeOrganizationCookieName,
    )?.value;
    const activeOrganizationId =
      memberships.find(
        (membership) => membership.organizationId === requestedOrganizationId,
      )?.organizationId ?? memberships[0]?.organizationId;
    const entitlements = await loadEntitlements(activeOrganizationId);
    return composeSession(
      identity,
      memberships,
      activeOrganizationId,
      entitlements,
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      return anonymousSession;
    }
    throw error;
  }
});
