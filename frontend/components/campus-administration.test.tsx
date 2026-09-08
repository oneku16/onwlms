import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CampusAdministration } from "@/components/campus-administration";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

describe("CampusAdministration", () => {
  it("creates a campus with tenant, CSRF, and idempotency context", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "campus-1",
          organization_id: "org-1",
          code: "NV",
          name: "North Valley",
          active: true,
        }),
        { status: 201, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <CampusAdministration
        canManage
        initialCampuses={{ items: [], total: 0 }}
        organizationId="org-1"
      />,
    );

    expect(screen.getByText("No campuses are available.")).toBeVisible();
    fireEvent.change(screen.getByLabelText(/^Campus code/), {
      target: { value: "nv" },
    });
    fireEvent.change(screen.getByLabelText("Campus name"), {
      target: { value: "North Valley" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create campus" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/campuses");
    expect(options.method).toBe("POST");
    const headers = new Headers(options.headers);
    expect(headers.get("x-csrf-token")).toBe("csrf-value");
    expect(headers.get("x-organization-id")).toBe("org-1");
    expect(headers.get("idempotency-key")).toMatch(/[0-9a-f-]{36}/);
    expect(JSON.parse(String(options.body))).toEqual({
      code: "NV",
      name: "North Valley",
    });
    expect(
      await screen.findByText("Campus “North Valley” was created."),
    ).toBeVisible();
    expect(screen.getByText("1 result")).toBeVisible();
  });

  it("disables creation without the campus permission", () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    render(
      <CampusAdministration
        canManage={false}
        initialCampuses={{ items: [], total: 0 }}
        organizationId="org-1"
      />,
    );
    expect(
      screen.getByRole("button", { name: "Create campus" }),
    ).toBeDisabled();
    expect(
      screen.getByText("Your current membership cannot manage campuses."),
    ).toBeVisible();
  });
});
