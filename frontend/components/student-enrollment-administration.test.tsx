import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StudentEnrollmentAdministration } from "@/components/student-enrollment-administration";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

const activeEnrollment = {
  id: "enrollment-1",
  studentId: "student-1",
  programId: "program-1",
  academicYearId: "year-1",
  cohortId: null,
  status: "active",
  enrolledAt: "2026-08-07T10:00:00Z",
};

function renderAdministration() {
  return render(
    <StudentEnrollmentAdministration
      academicYears={[{ id: "year-1", title: "2026/2027" }]}
      canManage
      cohorts={[]}
      initialEnrollments={[activeEnrollment]}
      organizationId="org-1"
      programs={[{ id: "program-1", title: "Computer Science" }]}
      students={[{ id: "student-1", title: "Student profile" }]}
    />,
  );
}

describe("StudentEnrollmentAdministration", () => {
  it("enrolls a student without a cohort using an ISO enrollment time", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "enrollment-1",
          student_id: "student-1",
          program_id: "program-1",
          academic_year_id: "year-1",
          cohort_id: null,
          enrolled_at: "2026-09-01T08:00:00Z",
          status: "active",
        }),
        { status: 201, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <StudentEnrollmentAdministration
        academicYears={[{ id: "year-1", title: "2026/2027" }]}
        canManage
        cohorts={[]}
        initialEnrollments={[]}
        organizationId="org-1"
        programs={[{ id: "program-1", title: "Computer Science" }]}
        students={[{ id: "student-1", title: "Student profile" }]}
      />,
    );

    fireEvent.change(screen.getByLabelText("Student profile"), {
      target: { value: "student-1" },
    });
    fireEvent.change(screen.getByLabelText("Program"), {
      target: { value: "program-1" },
    });
    fireEvent.change(screen.getByLabelText("Academic year"), {
      target: { value: "year-1" },
    });
    fireEvent.change(screen.getByLabelText("Enrolled at"), {
      target: { value: "2026-09-01T08:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Enroll student" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/academics/student-enrollments");
    expect(options.method).toBe("POST");
    const headers = new Headers(options.headers);
    expect(headers.get("x-csrf-token")).toBe("csrf-value");
    expect(headers.get("x-organization-id")).toBe("org-1");
    expect(JSON.parse(String(options.body))).toEqual({
      student_id: "student-1",
      program_id: "program-1",
      academic_year_id: "year-1",
      cohort_id: null,
      enrolled_at: new Date("2026-09-01T08:00").toISOString(),
    });
    expect(
      await screen.findByText(
        "Student profile was enrolled in Computer Science.",
      ),
    ).toBeVisible();
    expect(screen.getByText("active")).toBeVisible();
  });
  it("withdraws an active enrollment with a required explanation", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "enrollment-1",
          student_id: "student-1",
          program_id: "program-1",
          academic_year_id: "year-1",
          cohort_id: null,
          status: "withdrawn",
          enrolled_at: "2026-08-07T10:00:00Z",
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderAdministration();

    fireEvent.click(
      screen.getByRole("button", { name: "Withdraw enrollment" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "An explanation is required to withdraw an enrollment.",
    );
    expect(fetchMock).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText(/^Withdrawal explanation for/), {
      target: { value: "Student left the program." },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Withdraw enrollment" }),
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe(
      "/api/v1/academics/student-enrollments/enrollment-1/withdraw",
    );
    expect(options.method).toBe("POST");
    expect(new Headers(options.headers).get("x-csrf-token")).toBe("csrf-value");
    expect(JSON.parse(String(options.body))).toEqual({
      explanation: "Student left the program.",
    });
    expect(screen.getByText("withdrawn")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Withdraw enrollment" }),
    ).toBeNull();
  });
});
