import { describe, expect, it } from "vitest";

import type { SessionView } from "@/lib/api/session";
import { visibleNavigation } from "@/lib/navigation";

const organization = {
  id: "organization-1",
  displayName: "North Valley University",
  locale: "en",
  timezone: "UTC",
  branding: {
    primaryColor: "#173f5f",
    accentColor: "#f0a43c",
  },
};

function session(overrides: Partial<SessionView>): SessionView {
  return {
    authenticated: true,
    actor: { id: "actor-1", displayName: "Alex Morgan" },
    activeOrganization: organization,
    memberships: [],
    roles: [],
    permissions: [],
    entitlements: [],
    ...overrides,
  };
}

function visibleHrefs(value: SessionView): readonly string[] {
  return visibleNavigation(value).flatMap(({ items }) =>
    items.map(({ href }) => href),
  );
}

describe("permission- and entitlement-aware navigation", () => {
  it("shows Moodle deadlines only with both backend permission and entitlement", () => {
    const withoutEntitlement = session({
      roles: ["Student"],
      permissions: ["integrations.moodle_deadlines.read_own"],
    });
    const withEntitlement = session({
      ...withoutEntitlement,
      entitlements: ["moodle_integration"],
    });

    expect(visibleHrefs(withoutEntitlement)).not.toContain("/student/moodle");
    expect(visibleHrefs(withEntitlement)).toContain("/student/moodle");
  });

  it("offers grade amendment to permitted tenant administrators, not teachers", () => {
    const administrator = session({ roles: ["OrganizationAdmin"] });
    const reviser = session({
      roles: ["OrganizationAdmin"],
      permissions: ["grading.final_grade.revise"],
    });
    const teacher = session({
      roles: ["Teacher"],
      permissions: ["grading.final_grade.revise"],
    });

    expect(visibleHrefs(administrator)).not.toContain(
      "/organization/grade-amendments",
    );
    expect(visibleHrefs(reviser)).toContain("/organization/grade-amendments");
    expect(visibleHrefs(teacher)).not.toContain(
      "/organization/grade-amendments",
    );
    expect(visibleHrefs(teacher)).not.toContain("/teacher/grade-amendment");
  });
});
