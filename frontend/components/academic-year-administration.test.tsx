import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AcademicYearAdministration } from "@/components/academic-year-administration";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

describe("AcademicYearAdministration", () => {
  it("creates an academic year with plain calendar dates", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "year-1",
          name: "2026/2027",
          starts_on: "2026-09-01",
          ends_on: "2027-06-30",
        }),
        { status: 201, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <AcademicYearAdministration
        canManage
        initialAcademicYears={{ items: [], total: 0 }}
        organizationId="org-1"
      />,
    );

    fireEvent.change(screen.getByLabelText("Academic year name"), {
      target: { value: "2026/2027" },
    });
    fireEvent.change(screen.getByLabelText("Starts on"), {
      target: { value: "2026-09-01" },
    });
    fireEvent.change(screen.getByLabelText("Ends on"), {
      target: { value: "2027-06-30" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Create academic year" }),
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/academics/academic-years");
    expect(options.method).toBe("POST");
    const headers = new Headers(options.headers);
    expect(headers.get("x-csrf-token")).toBe("csrf-value");
    expect(headers.get("x-organization-id")).toBe("org-1");
    expect(JSON.parse(String(options.body))).toEqual({
      name: "2026/2027",
      starts_on: "2026-09-01",
      ends_on: "2027-06-30",
    });
    expect(
      await screen.findByText("Academic year “2026/2027” was created."),
    ).toBeVisible();
    expect(screen.getByText("2026-09-01 – 2027-06-30")).toBeVisible();
  });
});
