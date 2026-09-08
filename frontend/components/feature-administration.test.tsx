import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FeatureAdministration } from "@/components/feature-administration";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

describe("FeatureAdministration", () => {
  it("registers an unregistered feature code as a platform action", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "feature-2",
          code: "moodle_integration",
          display_name: "Moodle integration",
          base_included: false,
        }),
        { status: 201, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <FeatureAdministration
        initialFeatures={[
          {
            id: "feature-1",
            code: "academic",
            displayName: "Academic core",
            baseIncluded: true,
          },
        ]}
      />,
    );

    expect(
      screen.queryByRole("option", { name: "academic" }),
    ).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Feature code"), {
      target: { value: "moodle_integration" },
    });
    fireEvent.change(screen.getByLabelText("Display name"), {
      target: { value: "Moodle integration" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Register feature" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/platform/features");
    expect(options.method).toBe("POST");
    const headers = new Headers(options.headers);
    expect(headers.get("x-csrf-token")).toBe("csrf-value");
    expect(headers.get("x-organization-id")).toBeNull();
    expect(JSON.parse(String(options.body))).toEqual({
      code: "moodle_integration",
      display_name: "Moodle integration",
    });
    expect(
      await screen.findByText("Feature “Moodle integration” was registered."),
    ).toBeVisible();
    expect(screen.getByText("2 features")).toBeVisible();
    expect(
      screen.queryByRole("option", { name: "moodle_integration" }),
    ).not.toBeInTheDocument();
  });
});
