import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PlanAdministration } from "@/components/plan-administration";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

describe("PlanAdministration", () => {
  it("creates a plan with unlimited and bounded feature grants", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "plan-1",
          code: "campus",
          display_name: "Campus",
          active: true,
          grants: [
            { feature: "academic", usage_limit: null },
            { feature: "mcp", usage_limit: { amount: 1000, period: "month" } },
          ],
        }),
        { status: 201, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<PlanAdministration initialPlans={[]} />);

    expect(screen.getByText("No plans are configured.")).toBeVisible();
    fireEvent.change(screen.getByLabelText("Plan code"), {
      target: { value: "campus" },
    });
    fireEvent.change(screen.getByLabelText("Display name"), {
      target: { value: "Campus" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add feature grant" }));
    fireEvent.click(screen.getByRole("button", { name: "Add feature grant" }));
    fireEvent.change(screen.getByLabelText("Grant 1 feature"), {
      target: { value: "academic" },
    });
    fireEvent.change(screen.getByLabelText("Grant 2 feature"), {
      target: { value: "mcp" },
    });
    fireEvent.change(screen.getByLabelText(/^Grant 2 usage amount/), {
      target: { value: "1000" },
    });
    fireEvent.change(screen.getByLabelText("Grant 2 usage period"), {
      target: { value: "month" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create plan" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/platform/plans");
    expect(options.method).toBe("POST");
    const headers = new Headers(options.headers);
    expect(headers.get("x-csrf-token")).toBe("csrf-value");
    expect(headers.get("x-organization-id")).toBeNull();
    expect(headers.get("idempotency-key")).toMatch(/[0-9a-f-]{36}/);
    expect(JSON.parse(String(options.body))).toEqual({
      code: "campus",
      display_name: "Campus",
      grants: [
        { feature: "academic", usage_limit: null },
        { feature: "mcp", usage_limit: { amount: 1000, period: "month" } },
      ],
    });
    expect(await screen.findByText("Plan “Campus” was created.")).toBeVisible();
    expect(
      screen.getByText("academic · unlimited; mcp · 1,000 per month"),
    ).toBeVisible();
  });
});
