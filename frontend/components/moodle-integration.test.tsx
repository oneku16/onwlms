import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MoodleIntegration } from "@/components/moodle-integration";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

const disabledStatus = {
  configured: false,
  baseUrl: null,
  status: "disabled",
  lastSuccessAt: null,
  lastErrorCode: null,
  gradeEventsConfigured: false,
};

describe("MoodleIntegration", () => {
  it("saves the configuration without ever rendering the token", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          configured: true,
          base_url: "https://moodle.example.test",
          status: "configured",
          last_success_at: null,
          last_error_code: null,
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <MoodleIntegration
        canConfigure
        initialStatus={disabledStatus}
        organizationId="org-1"
      />,
    );

    expect(screen.getByText("No")).toBeVisible();
    fireEvent.change(screen.getByLabelText(/^Moodle base URL/), {
      target: { value: "https://moodle.example.test" },
    });
    fireEvent.change(screen.getByLabelText(/^Web service token/), {
      target: { value: "secret-token" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Save Moodle configuration" }),
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/integrations/moodle/configuration");
    expect(options.method).toBe("PUT");
    const headers = new Headers(options.headers);
    expect(headers.get("x-csrf-token")).toBe("csrf-value");
    expect(headers.get("x-organization-id")).toBe("org-1");
    expect(JSON.parse(String(options.body))).toEqual({
      base_url: "https://moodle.example.test",
      token: "secret-token",
    });
    expect(
      await screen.findByText(
        "Moodle configuration saved. The token is stored encrypted and is never displayed.",
      ),
    ).toBeVisible();
    expect(screen.getByText("Yes")).toBeVisible();
    expect(screen.getByLabelText(/^Web service token/)).toHaveValue("");
    expect(document.body.textContent).not.toContain("secret-token");
  });

  it("saves a grade-event secret and never renders it", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          configured: true,
          base_url: "https://moodle.example.test",
          status: "configured",
          last_success_at: null,
          last_error_code: null,
          grade_events_configured: true,
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <MoodleIntegration
        canConfigure
        initialStatus={disabledStatus}
        organizationId="org-1"
      />,
    );

    expect(screen.getByText("No signing secret")).toBeVisible();
    fireEvent.change(screen.getByLabelText(/^Grade-event signing secret/), {
      target: { value: "tenant-signing-secret-with-32-characters" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Save grade-event secret" }),
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/integrations/moodle/grade-event-secret");
    expect(options.method).toBe("PUT");
    expect(new Headers(options.headers).get("x-csrf-token")).toBe("csrf-value");
    expect(JSON.parse(String(options.body))).toEqual({
      secret: "tenant-signing-secret-with-32-characters",
    });
    expect(screen.getByText("Signing secret configured")).toBeVisible();
    expect(document.body.textContent).not.toContain(
      "tenant-signing-secret-with-32-characters",
    );
  });

  it("refuses a grade-event secret that is too short", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(
      <MoodleIntegration
        canConfigure
        initialStatus={disabledStatus}
        organizationId="org-1"
      />,
    );

    fireEvent.change(screen.getByLabelText(/^Grade-event signing secret/), {
      target: { value: "too-short" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Save grade-event secret" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Use at least 32 characters without leading or trailing spaces.",
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects non-https base URLs before contacting the backend", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(
      <MoodleIntegration
        canConfigure
        initialStatus={disabledStatus}
        organizationId="org-1"
      />,
    );

    fireEvent.change(screen.getByLabelText(/^Moodle base URL/), {
      target: { value: "http://moodle.example.test" },
    });
    fireEvent.change(screen.getByLabelText(/^Web service token/), {
      target: { value: "secret-token" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Save Moodle configuration" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Enter the Moodle base URL as an https:// address.",
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
