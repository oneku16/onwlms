import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TermAdministration } from "@/components/term-administration";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

describe("TermAdministration", () => {
  it("closes a selected term with explanation and CSRF protection", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "0198e706-a6d9-7b24-9156-7f92716f5f43",
          name: "Autumn 2026",
          is_closed: true,
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <TermAdministration
        academicYears={[]}
        canClose
        canManage
        organizationId="org-1"
        initialTerms={{
          total: 1,
          items: [
            {
              id: "0198e706-a6d9-7b24-9156-7f92716f5f43",
              title: "Autumn 2026",
              status: "open",
            },
          ],
        }}
      />,
    );

    fireEvent.change(screen.getByLabelText("Term"), {
      target: { value: "0198e706-a6d9-7b24-9156-7f92716f5f43" },
    });
    fireEvent.change(screen.getByLabelText(/^Closure explanation/), {
      target: { value: "Final results have been reviewed." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Close term" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe(
      "/api/v1/academics/terms/0198e706-a6d9-7b24-9156-7f92716f5f43/close",
    );
    expect(options.method).toBe("POST");
    expect(new Headers(options.headers).get("x-csrf-token")).toBe("csrf-value");
    expect(JSON.parse(String(options.body))).toEqual({
      explanation: "Final results have been reviewed.",
    });
    expect(
      await screen.findByText("“Autumn 2026” is now closed."),
    ).toBeVisible();
  });

  it("creates a term inside a selected academic year with an ISO deadline", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "term-2",
          academic_year_id: "year-1",
          name: "Spring 2027",
          starts_on: "2027-01-15",
          ends_on: "2027-05-30",
          enrollment_deadline: "2027-01-10T18:00:00Z",
          is_closed: false,
        }),
        { status: 201, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <TermAdministration
        academicYears={[{ id: "year-1", title: "2026/2027" }]}
        canClose={false}
        canManage
        organizationId="org-1"
        initialTerms={{ total: 0, items: [] }}
      />,
    );

    fireEvent.change(screen.getByLabelText("Academic year"), {
      target: { value: "year-1" },
    });
    fireEvent.change(screen.getByLabelText("Term name"), {
      target: { value: "Spring 2027" },
    });
    fireEvent.change(screen.getByLabelText("Starts on"), {
      target: { value: "2027-01-15" },
    });
    fireEvent.change(screen.getByLabelText("Ends on"), {
      target: { value: "2027-05-30" },
    });
    fireEvent.change(screen.getByLabelText(/^Enrollment deadline/), {
      target: { value: "2027-01-10T18:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create term" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/academics/terms");
    expect(options.method).toBe("POST");
    const headers = new Headers(options.headers);
    expect(headers.get("x-csrf-token")).toBe("csrf-value");
    expect(headers.get("x-organization-id")).toBe("org-1");
    const body = JSON.parse(String(options.body)) as Record<string, unknown>;
    expect(body).toEqual({
      academic_year_id: "year-1",
      name: "Spring 2027",
      starts_on: "2027-01-15",
      ends_on: "2027-05-30",
      enrollment_deadline: new Date("2027-01-10T18:00").toISOString(),
    });
    expect(
      await screen.findByText("Term “Spring 2027” was created."),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Close term" })).toBeDisabled();
  });
});
