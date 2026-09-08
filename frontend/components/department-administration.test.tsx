import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DepartmentAdministration } from "@/components/department-administration";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

describe("DepartmentAdministration", () => {
  it("creates a department under a selected faculty", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "department-1",
          faculty_id: "faculty-1",
          code: "CS",
          name: "Computer Science",
        }),
        { status: 201, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <DepartmentAdministration
        canManage
        faculties={[{ id: "faculty-1", title: "Engineering", code: "ENG" }]}
        initialDepartments={{ items: [], total: 0 }}
        organizationId="org-1"
      />,
    );

    fireEvent.change(screen.getByLabelText("Faculty"), {
      target: { value: "faculty-1" },
    });
    fireEvent.change(screen.getByLabelText("Department code"), {
      target: { value: "CS" },
    });
    fireEvent.change(screen.getByLabelText("Department name"), {
      target: { value: "Computer Science" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create department" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/academics/departments");
    expect(options.method).toBe("POST");
    const headers = new Headers(options.headers);
    expect(headers.get("x-csrf-token")).toBe("csrf-value");
    expect(headers.get("x-organization-id")).toBe("org-1");
    expect(JSON.parse(String(options.body))).toEqual({
      faculty_id: "faculty-1",
      code: "CS",
      name: "Computer Science",
    });
    expect(
      await screen.findByText("Department “Computer Science” was created."),
    ).toBeVisible();
  });
});
