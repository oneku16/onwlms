import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TeacherAssignmentAdministration } from "@/components/teacher-assignment-administration";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

describe("TeacherAssignmentAdministration", () => {
  it("assigns a tenant teacher to a labelled course offering", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "assignment-1",
          course_offering_id: "offering-1",
          teacher_id: "teacher-1",
          role: "lecturer",
        }),
        { status: 201, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <TeacherAssignmentAdministration
        canManage
        courses={[{ id: "course-1", title: "Programming I", code: "CS101" }]}
        initialAssignments={[]}
        offerings={[
          {
            id: "offering-1",
            courseId: "course-1",
            termId: "term-1",
            campusId: "campus-1",
            sectionCode: "A",
            capacity: 30,
            meetingWindows: [],
          },
        ]}
        organizationId="org-1"
        teachers={[{ id: "teacher-1", title: "Dr. Aitmatova" }]}
        terms={[{ id: "term-1", title: "Autumn 2026" }]}
      />,
    );

    fireEvent.change(screen.getByLabelText("Course offering"), {
      target: { value: "offering-1" },
    });
    fireEvent.change(screen.getByLabelText("Teacher profile"), {
      target: { value: "teacher-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Assign teacher" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/academics/teacher-assignments");
    expect(options.method).toBe("POST");
    const headers = new Headers(options.headers);
    expect(headers.get("x-csrf-token")).toBe("csrf-value");
    expect(headers.get("x-organization-id")).toBe("org-1");
    expect(JSON.parse(String(options.body))).toEqual({
      course_offering_id: "offering-1",
      teacher_id: "teacher-1",
      role: "lecturer",
    });
    expect(
      await screen.findByText(
        "Dr. Aitmatova was assigned to CS101 · Programming I · Autumn 2026 · Section A as lecturer.",
      ),
    ).toBeVisible();
    expect(screen.getByText("1 teacher assignment")).toBeVisible();
  });
});
