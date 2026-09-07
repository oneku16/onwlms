import { describe, expect, it } from "vitest";

import {
  parseGuardianGradeCollection,
  parseResourceCollection,
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
});
