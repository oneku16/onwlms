import { describe, expect, it } from "vitest";

import {
  parseMembershipAdministrations,
  parseOwnerLifecycles,
  parsePlatformAdministrators,
} from "@/lib/api/administration";

describe("administration response contracts", () => {
  it("parses membership lifecycle state without provider claims", () => {
    expect(
      parseMembershipAdministrations([
        {
          id: "0198a254-72d7-7000-8000-000000000001",
          organization_id: "0198a254-72d7-7000-8000-000000000002",
          identity_subject_id: "0198a254-72d7-7000-8000-000000000003",
          person_id: null,
          roles: ["student"],
          status: "suspended",
        },
      ])[0]?.status,
    ).toBe("suspended");
  });

  it("parses active and revoked platform assignments", () => {
    expect(
      parsePlatformAdministrators([
        {
          subject_id: "0198a254-72d7-7000-8000-000000000003",
          active: false,
        },
      ]),
    ).toEqual([
      {
        subjectId: "0198a254-72d7-7000-8000-000000000003",
        active: false,
      },
    ]);
  });

  it("parses the PII-free organization-owner lifecycle projection", () => {
    expect(
      parseOwnerLifecycles([
        {
          id: "0198a254-72d7-7000-8000-000000000004",
          organization_id: "0198a254-72d7-7000-8000-000000000002",
          status: "active",
        },
      ]),
    ).toEqual([
      {
        id: "0198a254-72d7-7000-8000-000000000004",
        organizationId: "0198a254-72d7-7000-8000-000000000002",
        status: "active",
      },
    ]);
  });
});
