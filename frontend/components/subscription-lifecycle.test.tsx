import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SubscriptionLifecycle } from "@/components/subscription-lifecycle";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

const organizations = [{ id: "org-1", title: "North Valley University" }];
const plans = [{ id: "plan-1", title: "Development base" }];

function subscriptionPayload(status: string): string {
  return JSON.stringify({
    id: "sub-1",
    organization_id: "org-1",
    plan_id: "plan-1",
    status,
    starts_at: "2026-08-01T00:00:00Z",
    ends_at: null,
  });
}

function jsonResponse(body: string, status = 200): Response {
  return new Response(body, {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("SubscriptionLifecycle", () => {
  it("suspends an active subscription and reflects the new state", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(subscriptionPayload("active")))
      .mockResolvedValueOnce(jsonResponse(subscriptionPayload("suspended")));
    vi.stubGlobal("fetch", fetchMock);
    render(
      <SubscriptionLifecycle organizations={organizations} plans={plans} />,
    );

    fireEvent.change(screen.getByLabelText("Organization"), {
      target: { value: "org-1" },
    });
    await waitFor(() => expect(screen.getByText("active")).toBeVisible());
    expect(screen.getByText("Development base")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Suspend" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [path, options] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(path).toBe(
      "/api/v1/platform/organizations/org-1/subscription/suspend",
    );
    expect(options.method).toBe("POST");
    expect(new Headers(options.headers).get("x-csrf-token")).toBe("csrf-value");
    expect(new Headers(options.headers).get("x-organization-id")).toBeNull();
    expect(
      await screen.findByText("The subscription is now suspended."),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Suspend" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reactivate" })).toBeEnabled();
  });

  it("reports an organization with no subscription without inventing one", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        jsonResponse(JSON.stringify({ detail: "Not found" }), 404),
      );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <SubscriptionLifecycle organizations={organizations} plans={plans} />,
    );

    fireEvent.change(screen.getByLabelText("Organization"), {
      target: { value: "org-1" },
    });

    expect(
      await screen.findByText(
        "This organization has no subscription to manage yet.",
      ),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Suspend" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Cancel subscription" }),
    ).toBeDisabled();
  });

  it("offers cancellation but not reactivation for a trialing subscription", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(subscriptionPayload("trialing")));
    vi.stubGlobal("fetch", fetchMock);
    render(
      <SubscriptionLifecycle organizations={organizations} plans={plans} />,
    );

    fireEvent.change(screen.getByLabelText("Organization"), {
      target: { value: "org-1" },
    });

    await waitFor(() => expect(screen.getByText("trialing")).toBeVisible());
    expect(screen.getByRole("button", { name: "Suspend" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Reactivate" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Cancel subscription" }),
    ).toBeEnabled();
  });
});
