import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProgramAdministration } from "@/components/program-administration";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

describe("ProgramAdministration", () => {
  it("creates a program with its education mode and credit label", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "program-1",
          department_id: "department-1",
          code: "BSCS",
          name: "Computer Science",
          education_mode: "flexible_selection",
          credit_unit_label: "ECTS",
        }),
        { status: 201, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <ProgramAdministration
        canManage
        departments={[{ id: "department-1", title: "Computer Science" }]}
        initialPrograms={{ items: [], total: 0 }}
        organizationId="org-1"
      />,
    );

    fireEvent.change(screen.getByLabelText("Department"), {
      target: { value: "department-1" },
    });
    fireEvent.change(screen.getByLabelText("Program code"), {
      target: { value: "BSCS" },
    });
    fireEvent.change(screen.getByLabelText("Program name"), {
      target: { value: "Computer Science" },
    });
    fireEvent.change(screen.getByLabelText("Education mode"), {
      target: { value: "flexible_selection" },
    });
    fireEvent.change(screen.getByLabelText("Credit unit label"), {
      target: { value: "ECTS" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create program" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/academics/programs");
    expect(options.method).toBe("POST");
    expect(new Headers(options.headers).get("x-csrf-token")).toBe("csrf-value");
    expect(JSON.parse(String(options.body))).toEqual({
      department_id: "department-1",
      code: "BSCS",
      name: "Computer Science",
      education_mode: "flexible_selection",
      credit_unit_label: "ECTS",
    });
    expect(
      await screen.findByText("Program “Computer Science” was created."),
    ).toBeVisible();
  });
});
