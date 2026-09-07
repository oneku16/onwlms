import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OwnerAppointmentForm } from "@/components/owner-appointment-form";
import type { OwnerLifecycleView } from "@/lib/api/administration";

const organization = {
  id: "0198e706-a6d9-7b24-9156-7f92716f5f40",
  title: "North School",
};

const owners: readonly OwnerLifecycleView[] = [
  {
    id: "0198e706-a6d9-7b24-9156-7f92716f5f47",
    organizationId: organization.id,
    status: "active",
  },
  {
    id: "0198e706-a6d9-7b24-9156-7f92716f5f48",
    organizationId: organization.id,
    status: "active",
  },
];

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

describe("OwnerAppointmentForm", () => {
  it("suspends a listed owner through the platform lifecycle endpoint", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: owners[0]?.id,
          organization_id: organization.id,
          status: "suspended",
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <OwnerAppointmentForm
        initialOwners={owners}
        organizations={[organization]}
      />,
    );

    fireEvent.click(screen.getAllByRole("button", { name: "Suspend" })[0]!);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe(
      `/api/v1/platform/organizations/${organization.id}/owners/${owners[0]?.id}/suspend`,
    );
    expect(options.method).toBe("POST");
    expect(new Headers(options.headers).get("x-csrf-token")).toBe("csrf-value");
    expect(await screen.findByText("suspended")).toBeVisible();
  });
});
