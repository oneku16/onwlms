import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GradeAmendmentForm } from "@/components/grade-amendment-form";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

describe("GradeAmendmentForm", () => {
  it("loads authorized choices and submits the verified revision number", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi
      .fn()
      .mockImplementation(
        async (input: RequestInfo | URL, options?: RequestInit) => {
          const path = String(input);
          if (path.includes("/grading/students/enrollment-1/transcript")) {
            return new Response(
              JSON.stringify([
                {
                  final_grade_id: "grade-1",
                  course_id: "course-1",
                  course_offering_id: "offering-1",
                  term_id: "term-1",
                  symbol: "B",
                },
              ]),
              { status: 200, headers: { "content-type": "application/json" } },
            );
          }
          if (options?.method !== "POST") {
            return new Response(
              JSON.stringify([
                { revision_number: 1 },
                { revision_number: 3 },
                { revision_number: 2 },
              ]),
              { status: 200, headers: { "content-type": "application/json" } },
            );
          }
          return new Response(
            JSON.stringify({ id: "grade-1", revision_number: 4 }),
            { status: 200, headers: { "content-type": "application/json" } },
          );
        },
      );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <GradeAmendmentForm
        canReviseClosedTerm={false}
        canSubmit
        courses={[{ id: "course-1", title: "Calculus" }]}
        enrollments={[
          {
            id: "enrollment-1",
            studentId: "student-1",
            programId: "program-1",
            status: "active",
          },
        ]}
        gradingScales={[{ id: "scale-1", name: "Undergraduate scale" }]}
        organizationId="org-1"
        programs={[{ id: "program-1", title: "BSc Mathematics" }]}
        students={[{ id: "student-1", title: "A. Student" }]}
        terms={[{ id: "term-1", title: "Fall 2026" }]}
      />,
    );

    fireEvent.change(screen.getByLabelText("Academic enrollment"), {
      target: { value: "enrollment-1" },
    });
    expect(
      await screen.findByRole("option", {
        name: "Calculus · Fall 2026 · B",
      }),
    ).toBeVisible();
    fireEvent.change(screen.getByLabelText("Official grade"), {
      target: { value: "grade-1" },
    });
    expect(await screen.findByText("Current revision: 3.")).toBeVisible();
    fireEvent.change(screen.getByLabelText("Revised raw score"), {
      target: { value: "91.5" },
    });
    fireEvent.change(
      screen.getByLabelText("Replacement grading scale (optional)"),
      {
        target: { value: "scale-1" },
      },
    );
    fireEvent.change(screen.getByLabelText(/^Amendment explanation/), {
      target: { value: "The source record was corrected." },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Record grade revision" }),
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const [path, options] = fetchMock.mock.calls[2] as [string, RequestInit];
    expect(path).toBe("/api/v1/grading/final-grades/grade-1/revisions");
    expect(new Headers(options.headers).get("x-csrf-token")).toBe("csrf-value");
    expect(JSON.parse(String(options.body))).toEqual({
      raw_score: "91.5",
      explanation: "The source record was corrected.",
      grading_scale_id: "scale-1",
      expected_revision_number: 3,
    });
    expect(
      await screen.findByText(
        "The official grade revision was recorded with its explanation.",
      ),
    ).toBeVisible();
    expect(screen.getByText("Current revision: 4.")).toBeVisible();
    expect(
      screen.queryByLabelText("Official grade identifier"),
    ).not.toBeInTheDocument();
  });
});
