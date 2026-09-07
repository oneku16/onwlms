import { describe, expect, it } from "vitest";

import {
  composeSession,
  parseCurrentIdentity,
  parseMembershipDiscoveries,
  parseOrganization,
} from "@/lib/api/session";

describe("session adapters", () => {
  it("parses the exact safe /auth/me identity contract", () => {
    const identity = parseCurrentIdentity({
      id: "actor-1",
      email: "alex@example.edu",
      display_name: "Alex Morgan",
      is_platform_admin: true,
      permissions: ["platform_administrators.manage"],
      expires_at: "2026-08-05T10:00:00+00:00",
    });

    expect(identity.actor).toEqual({
      id: "actor-1",
      email: "alex@example.edu",
      displayName: "Alex Morgan",
    });
    expect(identity.isPlatformAdmin).toBe(true);
    expect(identity.permissions).toEqual(["platform_administrators.manage"]);
  });

  it("accepts only active, complete membership discovery records", () => {
    expect(
      parseMembershipDiscoveries([
        {
          id: "membership-1",
          organization_id: "organization-1",
          roles: ["organization_admin", "teacher"],
          permissions: ["people.memberships.manage", "scheduling.read"],
          status: "active",
        },
        {
          id: "membership-2",
          organization_id: "organization-2",
          roles: ["student"],
          permissions: ["academics.student.read_own"],
          status: "suspended",
        },
      ]),
    ).toEqual([
      {
        id: "membership-1",
        organizationId: "organization-1",
        roles: ["OrganizationAdmin", "Teacher"],
        permissions: ["people.memberships.manage", "scheduling.read"],
      },
    ]);
  });

  it("composes active tenant roles and exact backend permissions", () => {
    const organization = parseOrganization({
      id: "organization-1",
      slug: "north-valley",
      branding: {
        display_name: "North Valley University",
        primary_color: "#123456",
        secondary_color: "not-a-color",
      },
      configuration: {
        locale: "en",
        timezone: "Asia/Bishkek",
      },
    });
    const result = composeSession(
      {
        actor: { id: "actor-1", displayName: "Alex Morgan" },
        isPlatformAdmin: false,
        permissions: [],
        expiresAt: "2026-08-05T10:00:00+00:00",
      },
      [
        {
          id: "membership-1",
          organizationId: organization.id,
          organization,
          roles: ["OrganizationAdmin"],
          permissions: ["scheduling.session.manage"],
        },
      ],
      organization.id,
      ["moodle_integration"],
    );

    expect(result.roles).toEqual(["OrganizationAdmin"]);
    expect(result.permissions).toContain("scheduling.session.manage");
    expect(result.entitlements).toEqual(["moodle_integration"]);
    expect(result.activeOrganization?.branding).toMatchObject({
      primaryColor: "#123456",
      accentColor: "#f0a43c",
    });
  });
});
