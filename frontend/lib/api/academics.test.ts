import { describe, expect, it } from "vitest";

import {
  parseAcademicYearCollection,
  parseCalendarEventSummary,
  parseCourseOfferings,
  parseCurriculum,
  parseSelectionPolicy,
  parseStudentEnrollments,
  parseTeacherAssignments,
} from "@/lib/api/academics";

describe("academic administration contracts", () => {
  it("summarizes academic years with their date range", () => {
    expect(
      parseAcademicYearCollection([
        {
          id: "year-1",
          name: "2026/2027",
          starts_on: "2026-09-01",
          ends_on: "2027-06-30",
        },
      ]),
    ).toEqual({
      items: [
        {
          id: "year-1",
          title: "2026/2027",
          subtitle: "2026-09-01 – 2027-06-30",
        },
      ],
      total: 1,
    });
  });

  it("labels calendar events by instruction allowance", () => {
    expect(
      parseCalendarEventSummary({
        id: "event-1",
        title: "Independence Day",
        starts_at: "2026-08-31T00:00:00Z",
        ends_at: "2026-09-01T00:00:00Z",
        instruction_allowed: false,
      }),
    ).toEqual({
      id: "event-1",
      title: "Independence Day",
      subtitle: "Ends 2026-09-01T00:00:00Z",
      status: "no instruction",
      occursAt: "2026-08-31T00:00:00Z",
    });
  });

  it("parses course offerings with ISO weekday meeting windows", () => {
    expect(
      parseCourseOfferings([
        {
          id: "offering-1",
          course_id: "course-1",
          term_id: "term-1",
          campus_id: "campus-1",
          section_code: "A",
          capacity: 30,
          meeting_windows: [
            { weekday: 1, starts_at: "09:00:00", ends_at: "10:30:00" },
          ],
        },
      ]),
    ).toEqual([
      {
        id: "offering-1",
        courseId: "course-1",
        termId: "term-1",
        campusId: "campus-1",
        sectionCode: "A",
        capacity: 30,
        meetingWindows: [
          { weekday: 1, startsAt: "09:00:00", endsAt: "10:30:00" },
        ],
      },
    ]);
    expect(() =>
      parseCourseOfferings([
        {
          id: "offering-1",
          course_id: "course-1",
          term_id: "term-1",
          campus_id: "campus-1",
          section_code: "A",
          capacity: 30,
          meeting_windows: [
            { weekday: 0, starts_at: "09:00:00", ends_at: "10:30:00" },
          ],
        },
      ]),
    ).toThrow("The meeting window response is not supported.");
  });

  it("parses teacher assignments and student enrollments", () => {
    expect(
      parseTeacherAssignments([
        {
          id: "assignment-1",
          course_offering_id: "offering-1",
          teacher_id: "teacher-1",
          role: "lecturer",
        },
      ]),
    ).toEqual([
      {
        id: "assignment-1",
        courseOfferingId: "offering-1",
        teacherId: "teacher-1",
        role: "lecturer",
      },
    ]);
    expect(
      parseStudentEnrollments([
        {
          id: "enrollment-1",
          student_id: "student-1",
          program_id: "program-1",
          academic_year_id: "year-1",
          cohort_id: null,
          enrolled_at: "2026-09-01T08:00:00Z",
          status: "active",
        },
      ]),
    ).toEqual([
      {
        id: "enrollment-1",
        studentId: "student-1",
        programId: "program-1",
        academicYearId: "year-1",
        cohortId: null,
        enrolledAt: "2026-09-01T08:00:00Z",
        status: "active",
      },
    ]);
  });

  it("parses curricula and course-selection policies", () => {
    expect(
      parseCurriculum({
        id: "curriculum-1",
        program_id: "program-1",
        academic_year_id: "year-1",
        courses: [
          {
            course_id: "course-1",
            kind: "required",
            credits: "6.00",
            prerequisite_course_ids: [],
          },
          { course_id: "course-2", kind: "elective", credits: "3.00" },
        ],
      }),
    ).toEqual({
      id: "curriculum-1",
      programId: "program-1",
      academicYearId: "year-1",
      courses: [
        {
          courseId: "course-1",
          kind: "required",
          credits: "6.00",
          prerequisiteCourseIds: [],
        },
        {
          courseId: "course-2",
          kind: "elective",
          credits: "3.00",
          prerequisiteCourseIds: [],
        },
      ],
    });
    expect(
      parseSelectionPolicy({
        program_id: "program-1",
        term_id: "term-1",
        approval_required: true,
        deadline: "2026-08-30T18:00:00Z",
        education_mode: "flexible_selection",
        maximum_credits: "30.00",
      }),
    ).toEqual({
      programId: "program-1",
      termId: "term-1",
      approvalRequired: true,
      deadline: "2026-08-30T18:00:00Z",
      educationMode: "flexible_selection",
      maximumCredits: "30.00",
    });
    expect(() =>
      parseSelectionPolicy({
        program_id: "program-1",
        term_id: "term-1",
        approval_required: true,
        deadline: "2026-08-30T18:00:00Z",
        education_mode: "unknown",
        maximum_credits: "30.00",
      }),
    ).toThrow("The course-selection policy response is not supported.");
  });
});
