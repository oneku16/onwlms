import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MembershipAdministration } from "@/components/membership-administration";
import type { MembershipAdministrationView } from "@/lib/api/administration";

const membership: MembershipAdministrationView = {
  id: "0198e706-a6d9-7b24-9156-7f92716f5f47",
  organizationId: "0198e706-a6d9-7b24-9156-7f92716f5f40",
  identitySubjectId: "0198e706-a6d9-7b24-9156-7f92716f5f41",
  personId: null,
  roles: ["student"],
  status: "active",
};

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

describe("MembershipAdministration", () => {
  it("transitions a listed membership with tenant and CSRF context", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: membership.id,
          organization_id: membership.organizationId,
          identity_subject_id: membership.identitySubjectId,
          person_id: null,
          roles: ["student"],
          status: "suspended",
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <MembershipAdministration
        canManage
        initialMemberships={[membership]}
        organizationId={membership.organizationId}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Suspend" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe(`/api/v1/memberships/${membership.id}/suspend`);
    expect(options.method).toBe("POST");
    const headers = new Headers(options.headers);
    expect(headers.get("x-csrf-token")).toBe("csrf-value");
    expect(headers.get("x-organization-id")).toBe(membership.organizationId);
    expect(await screen.findByText("suspended")).toBeVisible();
    expect(screen.getByRole("button", { name: "Reactivate" })).toBeVisible();
  });
});
