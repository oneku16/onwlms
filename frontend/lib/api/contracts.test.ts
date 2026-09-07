import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { operationalPages } from "@/lib/pages";

interface OpenApiOperation {
  readonly responses?: Readonly<
    Record<
      string,
      | {
          readonly content?: Readonly<
            Record<string, { readonly schema?: unknown } | undefined>
          >;
        }
      | undefined
    >
  >;
}

interface OpenApiDocument {
  readonly paths: Readonly<
    Record<
      string,
      Readonly<Record<string, OpenApiOperation | undefined>> | undefined
    >
  >;
}

const document = JSON.parse(
  readFileSync(resolve(process.cwd(), "../backend/openapi.json"), "utf8"),
) as OpenApiDocument;

const interactiveContracts = [
  ["post", "/api/v1/auth/login"],
  ["post", "/api/v1/auth/logout"],
  ["get", "/api/v1/entitlements/{feature}"],
  ["post", "/api/v1/platform/organizations"],
  ["post", "/api/v1/platform/organizations/{organization_id}/suspend"],
  ["post", "/api/v1/platform/organizations/{organization_id}/reactivate"],
  ["post", "/api/v1/platform/organizations/{organization_id}/owner"],
  ["get", "/api/v1/platform/organizations/{organization_id}/owners"],
  [
    "post",
    "/api/v1/platform/organizations/{organization_id}/owners/{membership_id}/suspend",
  ],
  [
    "post",
    "/api/v1/platform/organizations/{organization_id}/owners/{membership_id}/revoke",
  ],
  ["put", "/api/v1/platform/organizations/{organization_id}/subscription"],
  ["put", "/api/v1/platform/organizations/{organization_id}/entitlements"],
  ["post", "/api/v1/platform/administrators/{subject_id}/assign"],
  ["post", "/api/v1/platform/administrators/{subject_id}/revoke"],
  ["put", "/api/v1/memberships/{membership_id}/roles"],
  ["post", "/api/v1/memberships/{membership_id}/suspend"],
  ["post", "/api/v1/memberships/{membership_id}/reactivate"],
  ["post", "/api/v1/memberships/{membership_id}/revoke"],
  ["post", "/api/v1/academics/course-selection-requests"],
  [
    "patch",
    "/api/v1/academics/course-selection-requests/{request_id}/decision",
  ],
  ["post", "/api/v1/academics/terms/{term_id}/close"],
  ["get", "/api/v1/academics/student-enrollments"],
  ["get", "/api/v1/grading/scales"],
  ["get", "/api/v1/organizations/current/students"],
  ["get", "/api/v1/academics/programs"],
  ["get", "/api/v1/academics/courses"],
  ["get", "/api/v1/academics/terms"],
  [
    "get",
    "/api/v1/grading/students/{student_academic_enrollment_id}/transcript",
  ],
  ["post", "/api/v1/grading/final-grades/{final_grade_id}/revisions"],
  ["get", "/api/v1/grading/final-grades/{final_grade_id}/revisions"],
  ["get", "/api/v1/notifications/preferences"],
  ["put", "/api/v1/notifications/preferences/{channel}"],
  ["post", "/api/v1/notifications/{notification_id}/read"],
  ["post", "/api/v1/notifications/{notification_id}/retry"],
  ["get", "/api/v1/scheduling/teacher-availability"],
  ["post", "/api/v1/scheduling/teacher-availability"],
  ["delete", "/api/v1/scheduling/teacher-availability/{window_id}"],
  ["get", "/api/v1/scheduling/sessions"],
  ["post", "/api/v1/scheduling/sessions"],
  ["patch", "/api/v1/scheduling/sessions/{session_id}"],
  ["patch", "/api/v1/scheduling/sessions/{session_id}/lock"],
  [
    "get",
    "/api/v1/self-service/teacher/assigned-sections/{section_id}/students",
  ],
] as const;

const typedReadContracts = [
  ["get", "/api/v1/auth/me"],
  ["get", "/api/v1/auth/memberships"],
  ["get", "/api/v1/memberships"],
  ["get", "/api/v1/platform/administrators"],
  ["get", "/api/v1/platform/features"],
  ["get", "/api/v1/platform/plans"],
] as const;

describe("frontend/backend API contracts", () => {
  it("keeps every configured collection page on a real GET operation", () => {
    for (const definition of Object.values(operationalPages)) {
      if (!definition.endpoint) {
        continue;
      }
      const path = definition.endpoint.replace(/\?.*$/, "");
      expect(document.paths[path]?.get, `${path} GET`).toBeDefined();
    }
  });

  it("keeps every interactive action on a real operation", () => {
    for (const [method, path] of interactiveContracts) {
      expect(document.paths[path]?.[method], `${path} ${method}`).toBeDefined();
    }
  });

  it("publishes concrete schemas for critical frontend read contracts", () => {
    for (const [method, path] of typedReadContracts) {
      const schema =
        document.paths[path]?.[method]?.responses?.["200"]?.content?.[
          "application/json"
        ]?.schema;
      const contract = `${path} ${method.toUpperCase()} response schema`;
      expect(schema, contract).toBeDefined();
      expect(schema, contract).not.toEqual({});
    }
  });

  it("does not expose the absent custom-role collection", () => {
    expect(
      Object.values(operationalPages).some(
        (definition) =>
          definition.endpoint === "/api/v1/organizations/current/roles",
      ),
    ).toBe(false);
  });
});
