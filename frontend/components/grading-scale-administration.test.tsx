import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GradingScaleAdministration } from "@/components/grading-scale-administration";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

function scaleResponse(name: string, kind: string) {
  return new Response(
    JSON.stringify({
      id: "scale-1",
      name,
      kind,
      minimum_score: "0.00",
      maximum_score: "100.00",
      bands: [
        {
          minimum_score: "50.00",
          symbol: "Pass",
          passing: true,
          grade_points: "4.0",
        },
        { minimum_score: "0.00", symbol: "Fail", passing: false },
      ],
    }),
    { status: 201, headers: { "content-type": "application/json" } },
  );
}

describe("GradingScaleAdministration", () => {
  it("copies a built-in template into the organization", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi
      .fn()
      .mockResolvedValue(scaleResponse("Percentage", "percentage"));
    vi.stubGlobal("fetch", fetchMock);
    render(
      <GradingScaleAdministration
        canManage
        initialScales={[]}
        organizationId="org-1"
      />,
    );

    expect(screen.getByText("No grading scales are available.")).toBeVisible();
    fireEvent.change(screen.getAllByLabelText("Scale name")[0]!, {
      target: { value: "Percentage" },
    });
    fireEvent.change(screen.getByLabelText("Template"), {
      target: { value: "percentage" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Create from template" }),
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/grading/scale-templates");
    expect(options.method).toBe("POST");
    const headers = new Headers(options.headers);
    expect(headers.get("x-csrf-token")).toBe("csrf-value");
    expect(headers.get("x-organization-id")).toBe("org-1");
    expect(headers.get("idempotency-key")).toMatch(/[0-9a-f-]{36}/);
    expect(JSON.parse(String(options.body))).toEqual({
      name: "Percentage",
      template: "percentage",
    });
    expect(
      await screen.findByText(
        "Grading scale “Percentage” was created from the template.",
      ),
    ).toBeVisible();
    expect(screen.getByText("1 grading scale")).toBeVisible();
    expect(
      screen.getByText(
        "Pass from 50.00 · passing · 4.0 grade points; Fail from 0.00 · not passing",
      ),
    ).toBeVisible();
  });

  it("creates a custom scale with editable grade bands", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi
      .fn()
      .mockResolvedValue(scaleResponse("Faculty custom", "custom"));
    vi.stubGlobal("fetch", fetchMock);
    render(
      <GradingScaleAdministration
        canManage
        initialScales={[]}
        organizationId="org-1"
      />,
    );

    fireEvent.change(screen.getAllByLabelText("Scale name")[1]!, {
      target: { value: "Faculty custom" },
    });
    fireEvent.change(screen.getByLabelText("Kind"), {
      target: { value: "custom" },
    });
    fireEvent.change(screen.getByLabelText("Minimum score"), {
      target: { value: "0" },
    });
    fireEvent.change(screen.getByLabelText("Maximum score"), {
      target: { value: "100" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add grade band" }));
    fireEvent.change(screen.getByLabelText("Band 1 minimum score"), {
      target: { value: "50" },
    });
    fireEvent.change(screen.getByLabelText("Band 1 symbol"), {
      target: { value: "Pass" },
    });
    fireEvent.change(screen.getByLabelText("Band 1 grade points (optional)"), {
      target: { value: "4.0" },
    });
    fireEvent.click(screen.getByLabelText("Band 1 is passing"));
    fireEvent.change(screen.getByLabelText("Band 2 minimum score"), {
      target: { value: "0" },
    });
    fireEvent.change(screen.getByLabelText("Band 2 symbol"), {
      target: { value: "Fail" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Create custom scale" }),
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/grading/scales");
    expect(options.method).toBe("POST");
    expect(new Headers(options.headers).get("x-csrf-token")).toBe("csrf-value");
    expect(JSON.parse(String(options.body))).toEqual({
      name: "Faculty custom",
      kind: "custom",
      minimum_score: "0",
      maximum_score: "100",
      bands: [
        {
          minimum_score: "50",
          symbol: "Pass",
          passing: true,
          grade_points: "4.0",
        },
        {
          minimum_score: "0",
          symbol: "Fail",
          passing: false,
          grade_points: null,
        },
      ],
    });
    expect(
      await screen.findByText("Grading scale “Faculty custom” was created."),
    ).toBeVisible();
  });

  it("disables both forms without the grading permission", () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    render(
      <GradingScaleAdministration
        canManage={false}
        initialScales={[]}
        organizationId="org-1"
      />,
    );
    expect(
      screen.getByRole("button", { name: "Create from template" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Create custom scale" }),
    ).toBeDisabled();
  });
});
