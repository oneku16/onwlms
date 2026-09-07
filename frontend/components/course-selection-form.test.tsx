import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CourseSelectionForm } from "@/components/course-selection-form";
import type { StudentCourseSelectionContext } from "@/lib/api/course-selection";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

describe("CourseSelectionForm", () => {
  it("submits the exact student-owned selection with CSRF and tenant context", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const requestId = "0198e706-a6d9-7b24-9156-7f92716f5f47";
    const enrollmentId = "0198e706-a6d9-7b24-9156-7f92716f5f43";
    const termId = "0198e706-a6d9-7b24-9156-7f92716f5f44";
    const offeringOne = "0198e706-a6d9-7b24-9156-7f92716f5f45";
    const offeringTwo = "0198e706-a6d9-7b24-9156-7f92716f5f46";
    const context: StudentCourseSelectionContext = {
      studentProfileId: "0198e706-a6d9-7b24-9156-7f92716f5f42",
      enrollments: [
        {
          id: enrollmentId,
          programId: "0198e706-a6d9-7b24-9156-7f92716f5f48",
          programName: "Computer Science",
          academicYearId: "0198e706-a6d9-7b24-9156-7f92716f5f49",
          terms: [
            {
              id: termId,
              name: "Autumn 2026",
              startsOn: "2026-09-01",
              endsOn: "2026-12-20",
              deadline: "2026-08-30T18:00:00Z",
              maximumCredits: "30.00",
              approvalRequired: true,
              offerings: [
                {
                  id: offeringOne,
                  courseId: "0198e706-a6d9-7b24-9156-7f92716f5f50",
                  courseCode: "CS101",
                  courseTitle: "Programming I",
                  sectionCode: "A",
                  credits: "6.00",
                  capacity: 30,
                  meetingWindows: [],
                },
                {
                  id: offeringTwo,
                  courseId: "0198e706-a6d9-7b24-9156-7f92716f5f51",
                  courseCode: "MATH101",
                  courseTitle: "Discrete Mathematics",
                  sectionCode: "B",
                  credits: "6.00",
                  capacity: 25,
                  meetingWindows: [],
                },
              ],
            },
          ],
        },
      ],
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: requestId,
          student_academic_enrollment_id: enrollmentId,
          term_id: termId,
          offering_ids: [offeringOne, offeringTwo],
          requested_credits: "12.00",
          status: "pending",
          override_reason: null,
          overridden_rules: ["schedule_conflict"],
          rejection_reason: null,
        }),
        { status: 201, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <CourseSelectionForm
        canSubmit
        context={context}
        organizationId="org-1"
      />,
    );

    fireEvent.click(screen.getByLabelText(/CS101 · Programming I/));
    fireEvent.click(screen.getByLabelText(/MATH101 · Discrete Mathematics/));
    fireEvent.click(
      screen.getByRole("button", { name: "Submit course selection" }),
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/academics/course-selection-requests");
    expect(options.method).toBe("POST");
    const headers = new Headers(options.headers);
    expect(headers.get("x-csrf-token")).toBe("csrf-value");
    expect(headers.get("x-organization-id")).toBe("org-1");
    expect(JSON.parse(String(options.body))).toEqual({
      student_academic_enrollment_id: enrollmentId,
      term_id: termId,
      offering_ids: [offeringOne, offeringTwo],
    });
    expect(
      await screen.findByText(
        `Course selection ${requestId} was submitted with 12.00 requested credits and is pending.`,
      ),
    ).toBeVisible();
  });
});
