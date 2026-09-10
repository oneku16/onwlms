import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CourseAdministration } from "@/components/course-administration";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

describe("CourseAdministration", () => {
  it("creates a course with decimal credits kept as a string", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "course-1",
          department_id: "department-1",
          code: "CS101",
          title: "Programming I",
          credits: "6.00",
        }),
        { status: 201, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <CourseAdministration
        canManage
        departments={[{ id: "department-1", title: "Computer Science" }]}
        initialCourses={{ items: [], total: 0 }}
        organizationId="org-1"
      />,
    );

    fireEvent.change(screen.getByLabelText("Department"), {
      target: { value: "department-1" },
    });
    fireEvent.change(screen.getByLabelText("Course code"), {
      target: { value: "CS101" },
    });
    fireEvent.change(screen.getByLabelText("Course title"), {
      target: { value: "Programming I" },
    });
    fireEvent.change(screen.getByLabelText(/^Credits/), {
      target: { value: "6.00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create course" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/academics/courses");
    expect(options.method).toBe("POST");
    expect(new Headers(options.headers).get("x-csrf-token")).toBe("csrf-value");
    expect(JSON.parse(String(options.body))).toEqual({
      department_id: "department-1",
      code: "CS101",
      title: "Programming I",
      credits: "6.00",
    });
    expect(
      await screen.findByText("Course “Programming I” was created."),
    ).toBeVisible();
  });

  it("rejects malformed credits before contacting the backend", () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(
      <CourseAdministration
        canManage
        departments={[{ id: "department-1", title: "Computer Science" }]}
        initialCourses={{ items: [], total: 0 }}
        organizationId="org-1"
      />,
    );

    fireEvent.change(screen.getByLabelText(/^Credits/), {
      target: { value: "six" },
    });
    fireEvent.submit(screen.getByRole("button", { name: "Create course" }));

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Enter credits as a positive decimal number.",
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
