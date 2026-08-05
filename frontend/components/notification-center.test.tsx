import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NotificationCenter } from "@/components/notification-center";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

describe("NotificationCenter", () => {
  it("updates recipient-owned preferences with CSRF and tenant context", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ channel: "email", enabled: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <NotificationCenter
        canManagePreferences
        canRetry
        initialNotifications={[]}
        initialPreferences={[
          { channel: "in_app", enabled: true },
          { channel: "email", enabled: false },
          { channel: "sms", enabled: false },
          { channel: "whatsapp", enabled: false },
          { channel: "telegram", enabled: false },
        ]}
        organizationId="org-1"
      />,
    );

    fireEvent.click(
      screen.getByRole("checkbox", { name: "Email notifications" }),
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/notifications/preferences/email");
    expect(options.method).toBe("PUT");
    expect(new Headers(options.headers).get("x-csrf-token")).toBe("csrf-value");
    expect(new Headers(options.headers).get("x-organization-id")).toBe("org-1");
    expect(JSON.parse(String(options.body))).toEqual({ enabled: true });
    expect(await screen.findByText("Email preference saved.")).toBeVisible();
  });

  it("retries only an eligible external delivery", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "0198e706-a6d9-7b24-9156-7f92716f5f43",
          channel: "email",
          subject: "Enrollment ready",
          body: "Your enrollment is ready.",
          status: "sent",
          created_at: "2026-08-05T06:00:00Z",
          read_at: null,
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <NotificationCenter
        canManagePreferences
        canRetry
        initialNotifications={[
          {
            id: "0198e706-a6d9-7b24-9156-7f92716f5f43",
            channel: "email",
            subject: "Enrollment ready",
            body: "Your enrollment is ready.",
            status: "retry",
            createdAt: "2026-08-05T06:00:00Z",
            readAt: null,
          },
        ]}
        initialPreferences={[]}
        organizationId="org-1"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Retry delivery" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "/api/v1/notifications/0198e706-a6d9-7b24-9156-7f92716f5f43/retry",
    );
    expect(await screen.findByText("sent")).toBeVisible();
  });
});
