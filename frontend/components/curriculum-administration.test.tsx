import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CurriculumAdministration } from "@/components/curriculum-administration";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

const notFound = () =>
  new Response(
    JSON.stringify({
      error: {
        code: "not_found",
        message: "Program curriculum was not found.",
      },
    }),
    { status: 404, headers: { "content-type": "application/json" } },
  );

function curriculumResponse(id: string) {
  return new Response(
    JSON.stringify({
      id,
      program_id: "program-1",
      academic_year_id: "year-1",
      courses: [
        {
          course_id: "course-1",
          kind: "required",
          credits: "6.00",
          prerequisite_course_ids: ["course-2"],
        },
      ],
    }),
    { status: 200, headers: { "content-type": "application/json" } },
  );
}

function renderEditor() {
  return render(
    <CurriculumAdministration
      academicYears={[{ id: "year-1", title: "2026/2027" }]}
      canManage
      courses={[
        { id: "course-1", title: "Programming I", code: "CS101" },
        { id: "course-2", title: "Mathematics", code: "MA101" },
      ]}
      organizationId="org-1"
      programs={[{ id: "program-1", title: "Computer Science" }]}
    />,
  );
}

describe("CurriculumAdministration", () => {
  it("creates a curriculum with a generated identifier when none exists", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi
      .fn()
      .mockImplementation(
        async (input: RequestInfo | URL, options?: RequestInit) => {
          if (options?.method === "PUT") {
            const path = String(input);
            return curriculumResponse(path.slice(path.lastIndexOf("/") + 1));
          }
          return notFound();
        },
      );
    vi.stubGlobal("fetch", fetchMock);
    renderEditor();

    fireEvent.change(screen.getByLabelText("Program"), {
      target: { value: "program-1" },
    });
    fireEvent.change(screen.getByLabelText("Academic year"), {
      target: { value: "year-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Load curriculum" }));

    expect(
      await screen.findByText(
        "No curriculum is configured for this program and academic year. Saving creates it.",
      ),
    ).toBeVisible();
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "/api/v1/academics/curricula?program_id=program-1&academic_year_id=year-1",
    );

    fireEvent.click(screen.getByRole("button", { name: "Add course row" }));
    fireEvent.change(screen.getByLabelText("Course 1"), {
      target: { value: "course-1" },
    });
    fireEvent.change(screen.getByLabelText("Credits 1"), {
      target: { value: "6.00" },
    });
    await userEvent.selectOptions(
      screen.getByLabelText(/^Prerequisites 1/),
      "course-2",
    );
    fireEvent.click(screen.getByRole("button", { name: "Save curriculum" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [path, options] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(path).toMatch(/^\/api\/v1\/academics\/curricula\/[0-9a-f-]{36}$/);
    expect(options.method).toBe("PUT");
    const headers = new Headers(options.headers);
    expect(headers.get("x-csrf-token")).toBe("csrf-value");
    expect(headers.get("x-organization-id")).toBe("org-1");
    expect(JSON.parse(String(options.body))).toEqual({
      program_id: "program-1",
      academic_year_id: "year-1",
      courses: [
        {
          course_id: "course-1",
          kind: "required",
          credits: "6.00",
          prerequisite_course_ids: ["course-2"],
        },
      ],
    });
    expect(
      await screen.findByText("Curriculum saved with 1 course."),
    ).toBeVisible();
    expect(screen.getByText("configured")).toBeVisible();
  });

  it("pre-fills rows from an existing curriculum", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(curriculumResponse("curriculum-1")),
    );
    renderEditor();

    fireEvent.change(screen.getByLabelText("Program"), {
      target: { value: "program-1" },
    });
    fireEvent.change(screen.getByLabelText("Academic year"), {
      target: { value: "year-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Load curriculum" }));

    expect(await screen.findByLabelText("Course 1")).toHaveValue("course-1");
    expect(screen.getByLabelText("Credits 1")).toHaveValue("6.00");
    expect(screen.getByLabelText(/^Prerequisites 1/)).toHaveValue(["course-2"]);
    expect(screen.getByText("Edit curriculum courses")).toBeVisible();
  });
});
