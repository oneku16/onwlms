import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CohortAdministration } from "@/components/cohort-administration";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

describe("CohortAdministration", () => {
  it("creates a cohort for a program and academic year", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "cohort-1",
          program_id: "program-1",
          academic_year_id: "year-1",
          code: "CS-26",
          name: "Computer Science 2026",
        }),
        { status: 201, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <CohortAdministration
        academicYears={[{ id: "year-1", title: "2026/2027" }]}
        canManage
        initialCohorts={{ items: [], total: 0 }}
        organizationId="org-1"
        programs={[{ id: "program-1", title: "Computer Science" }]}
      />,
    );

    fireEvent.change(screen.getByLabelText("Program"), {
      target: { value: "program-1" },
    });
    fireEvent.change(screen.getByLabelText("Academic year"), {
      target: { value: "year-1" },
    });
    fireEvent.change(screen.getByLabelText("Cohort code"), {
      target: { value: "CS-26" },
    });
    fireEvent.change(screen.getByLabelText("Cohort name"), {
      target: { value: "Computer Science 2026" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create cohort" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/academics/cohorts");
    expect(options.method).toBe("POST");
    expect(new Headers(options.headers).get("x-csrf-token")).toBe("csrf-value");
    expect(JSON.parse(String(options.body))).toEqual({
      program_id: "program-1",
      academic_year_id: "year-1",
      code: "CS-26",
      name: "Computer Science 2026",
    });
    expect(
      await screen.findByText("Cohort “Computer Science 2026” was created."),
    ).toBeVisible();
  });
});
