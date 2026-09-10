import { describe, expect, it } from "vitest";

import { parseGuardianRelationship, parseProfile } from "@/lib/api/people";

describe("people contracts", () => {
  it("parses profiles without local reference numbers", () => {
    expect(
      parseProfile({
        id: "profile-1",
        organization_id: "organization-1",
        person_id: "person-1",
        kind: "teacher",
        title: "Dr.",
      }),
    ).toEqual({
      id: "profile-1",
      personId: "person-1",
      kind: "teacher",
      title: "Dr.",
    });
    expect(
      parseProfile({
        id: "profile-2",
        organization_id: "organization-1",
        person_id: "person-1",
        kind: "student",
        title: null,
      }).title,
    ).toBeNull();
    expect(() =>
      parseProfile({ id: "profile-3", person_id: "person-1", kind: "alumni" }),
    ).toThrow("The profile response is not supported.");
  });

  it("parses guardian relationships by profile identifiers only", () => {
    expect(
      parseGuardianRelationship({
        id: "relationship-1",
        organization_id: "organization-1",
        guardian_profile_id: "guardian-1",
        student_profile_id: "student-1",
        relationship_label: "mother",
      }),
    ).toEqual({
      id: "relationship-1",
      guardianProfileId: "guardian-1",
      studentProfileId: "student-1",
      relationshipLabel: "mother",
    });
  });
});
