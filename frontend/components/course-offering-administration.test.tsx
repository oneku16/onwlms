import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CourseOfferingAdministration } from "@/components/course-offering-administration";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

describe("CourseOfferingAdministration", () => {
  it("creates an offering with ISO-weekday meeting windows", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "offering-1",
          course_id: "course-1",
          term_id: "term-1",
          campus_id: "campus-1",
          section_code: "A",
          capacity: 30,
          meeting_windows: [
            { weekday: 2, starts_at: "09:00:00", ends_at: "10:30:00" },
          ],
        }),
        { status: 201, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <CourseOfferingAdministration
        campuses={[{ id: "campus-1", title: "North Valley" }]}
        canManage
        courses={[{ id: "course-1", title: "Programming I", code: "CS101" }]}
        initialOfferings={[]}
        organizationId="org-1"
        terms={[{ id: "term-1", title: "Autumn 2026" }]}
      />,
    );

    fireEvent.change(screen.getByLabelText("Course"), {
      target: { value: "course-1" },
    });
    fireEvent.change(screen.getByLabelText("Term"), {
      target: { value: "term-1" },
    });
    fireEvent.change(screen.getByLabelText("Campus"), {
      target: { value: "campus-1" },
    });
    fireEvent.change(screen.getByLabelText("Section code"), {
      target: { value: "A" },
    });
    fireEvent.change(screen.getByLabelText("Capacity"), {
      target: { value: "30" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add meeting window" }));
    fireEvent.change(screen.getByLabelText("Weekday 1"), {
      target: { value: "2" },
    });
    fireEvent.change(screen.getByLabelText("Start time 1"), {
      target: { value: "09:00" },
    });
    fireEvent.change(screen.getByLabelText("End time 1"), {
      target: { value: "10:30" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Create course offering" }),
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/academics/course-offerings");
    expect(options.method).toBe("POST");
    const headers = new Headers(options.headers);
    expect(headers.get("x-csrf-token")).toBe("csrf-value");
    expect(headers.get("x-organization-id")).toBe("org-1");
    expect(JSON.parse(String(options.body))).toEqual({
      course_id: "course-1",
      term_id: "term-1",
      campus_id: "campus-1",
      section_code: "A",
      capacity: 30,
      meeting_windows: [{ weekday: 2, starts_at: "09:00", ends_at: "10:30" }],
    });
    expect(
      await screen.findByText(
        "Course offering “CS101 · Programming I · Autumn 2026 · Section A” was created.",
      ),
    ).toBeVisible();
    expect(screen.getByText("Tuesday 09:00:00–10:30:00")).toBeVisible();
  });
});
