import { describe, expect, it } from "vitest";

import {
  appendResource,
  parseGuardianGradeCollection,
  parseResourceCollection,
  resourceLabel,
  resourceTitle,
} from "@/lib/api/resources";

describe("resource projections", () => {
  it("keeps admissions applications visible without inventing applicant PII", () => {
    const collection = parseResourceCollection([
      {
        id: "0198e706-a6d9-7b24-9156-7f92716f5f43",
        applicant_profile_id: "0198e706-a6d9-7b24-9156-7f92716f5f44",
        program_id: "0198e706-a6d9-7b24-9156-7f92716f5f45",
        seat_category: "general",
        status: "submitted",
      },
    ]);

    expect(collection.items).toEqual([
      expect.objectContaining({
        id: "0198e706-a6d9-7b24-9156-7f92716f5f43",
        title: "Admissions application 0198e706",
        subtitle: "general",
        status: "submitted",
      }),
    ]);
  });

  it("renders the safe Moodle connection status as a real resource", () => {
    const collection = parseResourceCollection({
      configured: true,
      base_url: "https://moodle.example.test",
      status: "healthy",
    });

    expect(collection.items).toEqual([
      expect.objectContaining({
        title: "Moodle integration",
        subtitle: "https://moodle.example.test",
        status: "healthy",
      }),
    ]);
  });

  it("keeps GPA, earned credits, and quality points together", () => {
    const collection = parseResourceCollection({
      credits_attempted: "30",
      credits_earned: "27",
      gpa_credits_attempted: "24",
      quality_points: "84",
      gpa: "3.5",
    });

    expect(collection.items).toEqual([
      expect.objectContaining({
        title: "Official GPA and credits",
        subtitle: "GPA 3.5 · 27/30 credits earned · 84 quality points",
      }),
    ]);
  });

  it("renders room, provisioning, and audit response shapes without dropping rows", () => {
    const room = parseResourceCollection([
      {
        id: "room-1",
        campus_id: "campus-1",
        code: "A-101",
        room_type: "lecture",
        capacity: 40,
      },
    ]);
    const provisioning = parseResourceCollection([
      {
        id: "job-1",
        subject_type: "person",
        subject_id: "person-1",
        target: "moodle",
        status: "pending",
        attempts: 0,
        created_at: "2026-08-07T09:00:00Z",
        updated_at: "2026-08-07T09:00:00Z",
      },
    ]);
    const audit = parseResourceCollection([
      {
        id: "audit-1",
        organization_id: "organization-1",
        actor_subject_id: "subject-1",
        action: "membership.revoked",
        entity_type: "people_access",
        entity_id: "membership-1",
        occurred_at: "2026-08-07T09:00:00Z",
        source: "api",
        outcome: "succeeded",
        correlation_id: "correlation-1",
      },
    ]);

    expect(room.items[0]).toEqual(
      expect.objectContaining({
        title: "A-101 · lecture",
        subtitle: "Capacity 40",
      }),
    );
    expect(provisioning.items[0]).toEqual(
      expect.objectContaining({
        title: "moodle provisioning",
        subtitle: "person",
        status: "pending",
      }),
    );
    expect(audit.items[0]).toEqual(
      expect.objectContaining({
        title: "membership.revoked · people_access",
        subtitle: "membership-1",
      }),
    );
  });

  it("fails visibly instead of silently dropping an unsupported row", () => {
    expect(() => parseResourceCollection([{ unexpected: true }])).toThrow(
      "The resource collection response is not supported.",
    );
  });

  it("appends created resources and labels selections by code and title", () => {
    const campus = { id: "campus-1", title: "North Valley", code: "NV" };
    const appended = appendResource({ items: [], total: 0 }, campus);
    expect(appended).toEqual({ items: [campus], total: 1 });
    expect(appendResource({ items: [], total: null }, campus).total).toBeNull();
    expect(resourceLabel(campus)).toBe("NV · North Valley");
    expect(resourceLabel({ id: "p-1", title: "A. Person" })).toBe("A. Person");
    expect(resourceTitle([campus], "campus-1", "Campus")).toBe(
      "NV · North Valley",
    );
    expect(resourceTitle([], "0198e706-a6d9-7b24", "Campus")).toBe(
      "Campus 0198e706",
    );
  });

  it("flattens only authorized linked-student official grades", () => {
    const collection = parseGuardianGradeCollection([
      {
        student_person_id: "student-1",
        display_name: "A. Student",
        latest_official_grades: [
          {
            course_code: "MATH-101",
            course_title: "Calculus",
            display_grade: "A",
            credits_attempted: "3",
            credits_earned: "3",
            grade_points: "4.0",
          },
        ],
      },
    ]);

    expect(collection.items).toEqual([
      {
        id: "student-1:MATH-101:0",
        title: "MATH-101 · Calculus",
        subtitle: "A. Student · 3/3 credits earned",
        status: "A",
      },
    ]);
  });

  it("fails visibly instead of omitting a malformed official guardian grade", () => {
    expect(() =>
      parseGuardianGradeCollection([
        {
          student_person_id: "student-1",
          display_name: "A. Student",
          latest_official_grades: [
            {
              course_code: "MATH-101",
              course_title: "Calculus",
              display_grade: "A",
              grade_points: "4.0",
            },
          ],
        },
      ]),
    ).toThrow("The guardian grade response is not supported.");
  });
});
