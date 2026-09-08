import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FacultyAdministration } from "@/components/faculty-administration";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

describe("FacultyAdministration", () => {
  it("creates a faculty under a selected campus", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "faculty-1",
          campus_id: "campus-1",
          code: "ENG",
          name: "Engineering",
        }),
        { status: 201, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <FacultyAdministration
        campuses={[{ id: "campus-1", title: "North Valley", code: "NV" }]}
        canManage
        initialFaculties={{ items: [], total: 0 }}
        organizationId="org-1"
      />,
    );

    fireEvent.change(screen.getByLabelText("Campus"), {
      target: { value: "campus-1" },
    });
    fireEvent.change(screen.getByLabelText("Faculty code"), {
      target: { value: "ENG" },
    });
    fireEvent.change(screen.getByLabelText("Faculty name"), {
      target: { value: "Engineering" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create faculty" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/academics/faculties");
    expect(options.method).toBe("POST");
    const headers = new Headers(options.headers);
    expect(headers.get("x-csrf-token")).toBe("csrf-value");
    expect(headers.get("x-organization-id")).toBe("org-1");
    expect(JSON.parse(String(options.body))).toEqual({
      campus_id: "campus-1",
      code: "ENG",
      name: "Engineering",
    });
    expect(
      await screen.findByText("Faculty “Engineering” was created."),
    ).toBeVisible();
  });

  it("surfaces backend rejection messages", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: "conflict",
              message: "Faculty code already exists.",
            },
          }),
          { status: 409, headers: { "content-type": "application/json" } },
        ),
      ),
    );
    render(
      <FacultyAdministration
        campuses={[{ id: "campus-1", title: "North Valley" }]}
        canManage
        initialFaculties={{ items: [], total: 0 }}
        organizationId="org-1"
      />,
    );

    fireEvent.change(screen.getByLabelText("Campus"), {
      target: { value: "campus-1" },
    });
    fireEvent.change(screen.getByLabelText("Faculty code"), {
      target: { value: "ENG" },
    });
    fireEvent.change(screen.getByLabelText("Faculty name"), {
      target: { value: "Engineering" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create faculty" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Faculty code already exists.",
    );
  });
});
