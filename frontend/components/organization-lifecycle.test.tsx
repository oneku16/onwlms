import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OrganizationLifecycle } from "@/components/organization-lifecycle";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

describe("OrganizationLifecycle", () => {
  it("suspends a listed organization through the governed endpoint", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const organizationId = "0198e706-a6d9-7b24-9156-7f92716f5f40";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: organizationId,
          slug: "north-university",
          organization_type: "university",
          status: "suspended",
          branding: { display_name: "North University" },
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <OrganizationLifecycle
        initialOrganizations={[
          {
            id: organizationId,
            title: "North University",
            status: "active",
          },
        ]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Suspend" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe(
      `/api/v1/platform/organizations/${organizationId}/suspend`,
    );
    expect(new Headers(options.headers).get("x-csrf-token")).toBe("csrf-value");
    expect(await screen.findByText("suspended")).toBeVisible();
    expect(screen.getByRole("button", { name: "Reactivate" })).toBeVisible();
  });
});
