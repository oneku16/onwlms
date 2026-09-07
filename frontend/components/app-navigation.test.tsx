import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AppNavigation } from "@/components/app-navigation";
import type { SessionView } from "@/lib/api/session";

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
}));

const organization = {
  id: "0198c1c0-1111-7000-8000-000000000001",
  displayName: "North Valley University",
  slug: "north-valley",
  locale: "en",
  timezone: "UTC",
  branding: {
    primaryColor: "#173f5f",
    accentColor: "#f0a43c",
  },
} as const;

function session(overrides: Partial<SessionView> = {}): SessionView {
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

describe("AppNavigation", () => {
  it("keeps tenant academic navigation out of a platform-only session", () => {
    render(
      <AppNavigation
        pathname="/platform/organizations"
        session={session({
          activeOrganization: null,
          roles: ["PlatformAdmin"],
          permissions: ["organizations.platform.lifecycle"],
        })}
      />,
    );

    expect(screen.getByRole("link", { name: "Organizations" })).toBeVisible();
    expect(
      screen.queryByRole("link", { name: "Campuses" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Official grades" }),
    ).not.toBeInTheDocument();
  });

  it("requires both permission and entitlement for optional tenant capabilities", () => {
    const permitted = session({
      roles: ["OrganizationAdmin"],
      permissions: ["integrations.read", "people.memberships.manage"],
      entitlements: ["moodle_integration"],
    });
    render(<AppNavigation session={permitted} />);

    expect(screen.getByRole("link", { name: "Moodle status" })).toBeVisible();
    expect(
      screen.queryByRole("link", { name: "Roles and permissions" }),
    ).not.toBeInTheDocument();
  });

  it("uses explicit permissions for staff and guest tools without job-title checks", () => {
    render(
      <AppNavigation
        session={session({
          roles: ["Guest"],
          permissions: ["provisioning.read"],
        })}
      />,
    );

    expect(
      screen.getByRole("link", { name: "Operations workspace" }),
    ).toBeVisible();
    expect(
      screen.queryByRole("link", { name: "Academic workspace" }),
    ).not.toBeInTheDocument();
  });
});
