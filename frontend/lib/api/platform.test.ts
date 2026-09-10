import { describe, expect, it } from "vitest";

import {
  parseFeatures,
  parsePlans,
  parseSubscription,
} from "@/lib/api/platform";

describe("platform catalog contracts", () => {
  it("parses plans with explicit grants and optional usage limits", () => {
    expect(
      parsePlans([
        {
          id: "plan-1",
          code: "campus",
          display_name: "Campus",
          active: true,
          grants: [
            { feature: "academic", usage_limit: null },
            { feature: "mcp", usage_limit: { amount: 1000, period: "month" } },
          ],
        },
      ]),
    ).toEqual([
      {
        id: "plan-1",
        code: "campus",
        displayName: "Campus",
        active: true,
        grants: [
          { feature: "academic", usageLimit: null },
          { feature: "mcp", usageLimit: { amount: 1000, period: "month" } },
        ],
      },
    ]);
    expect(() =>
      parsePlans([
        {
          id: "plan-2",
          code: "x",
          display_name: "X",
          active: true,
          grants: [{ feature: "unknown", usage_limit: null }],
        },
      ]),
    ).toThrow("The plan grant response is not supported.");
  });

  it("parses features and rejects unknown codes", () => {
    expect(
      parseFeatures([
        {
          id: "feature-1",
          code: "moodle_integration",
          display_name: "Moodle integration",
          base_included: false,
        },
      ]),
    ).toEqual([
      {
        id: "feature-1",
        code: "moodle_integration",
        displayName: "Moodle integration",
        baseIncluded: false,
      },
    ]);
    expect(() =>
      parseFeatures([
        { id: "f", code: "unknown", display_name: "U", base_included: true },
      ]),
    ).toThrow("The feature response is not supported.");
  });
});

describe("subscription contract", () => {
  it("parses one organization's current subscription lifecycle", () => {
    expect(
      parseSubscription({
        id: "sub-1",
        organization_id: "org-1",
        plan_id: "plan-1",
        status: "suspended",
        starts_at: "2026-08-01T00:00:00Z",
        ends_at: null,
      }),
    ).toEqual({
      id: "sub-1",
      organizationId: "org-1",
      planId: "plan-1",
      status: "suspended",
      startsAt: "2026-08-01T00:00:00Z",
      endsAt: null,
    });
  });

  it("rejects an unsupported subscription status", () => {
    expect(() =>
      parseSubscription({
        id: "sub-1",
        organization_id: "org-1",
        plan_id: "plan-1",
        status: "expired",
        starts_at: "2026-08-01T00:00:00Z",
        ends_at: null,
      }),
    ).toThrow("The subscription response is not supported.");
  });
});
