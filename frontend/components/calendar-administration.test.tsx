import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CalendarAdministration } from "@/components/calendar-administration";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

describe("CalendarAdministration", () => {
  it("creates a closure event with explicit instruction allowance", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "event-1",
          title: "Independence Day",
          starts_at: "2026-08-31T00:00:00Z",
          ends_at: "2026-09-01T00:00:00Z",
          instruction_allowed: false,
        }),
        { status: 201, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <CalendarAdministration
        canManage
        initialEvents={{ items: [], total: 0 }}
        organizationId="org-1"
      />,
    );

    fireEvent.change(screen.getByLabelText("Event title"), {
      target: { value: "Independence Day" },
    });
    fireEvent.change(screen.getByLabelText("Starts at"), {
      target: { value: "2026-08-31T00:00" },
    });
    fireEvent.change(screen.getByLabelText("Ends at"), {
      target: { value: "2026-09-01T00:00" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Create calendar event" }),
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/academics/calendar-events");
    expect(options.method).toBe("POST");
    expect(new Headers(options.headers).get("x-csrf-token")).toBe("csrf-value");
    expect(JSON.parse(String(options.body))).toEqual({
      title: "Independence Day",
      starts_at: new Date("2026-08-31T00:00").toISOString(),
      ends_at: new Date("2026-09-01T00:00").toISOString(),
      instruction_allowed: false,
    });
    expect(
      await screen.findByText("Calendar event “Independence Day” was created."),
    ).toBeVisible();
    expect(screen.getByText("no instruction")).toBeVisible();
  });
});
