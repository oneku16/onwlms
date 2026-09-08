import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdmissionsPolicyAdministration } from "@/components/admissions-policy-administration";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

function json(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const notFound = () =>
  json({ error: { code: "not_found", message: "Not configured." } }, 404);

function renderAdministration() {
  return render(
    <AdmissionsPolicyAdministration
      canManage
      organizationId="org-1"
      programs={[{ id: "program-1", title: "Computer Science" }]}
      terms={[{ id: "term-1", title: "Autumn 2026" }]}
    />,
  );
}

describe("AdmissionsPolicyAdministration", () => {
  it("configures a missing admissions policy for a program and intake", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi
      .fn()
      .mockImplementation(
        async (_input: RequestInfo | URL, options?: RequestInit) =>
          options?.method === "PUT"
            ? json({
                program_id: "program-1",
                intake_id: "term-1",
                required_stages: ["exam", "interview"],
                deposit_required: true,
                deposit_amount: "150.00",
                deposit_currency: "USD",
                reservation_duration_seconds: 86400,
              })
            : notFound(),
      );
    vi.stubGlobal("fetch", fetchMock);
    renderAdministration();

    fireEvent.change(screen.getByLabelText("Policy program"), {
      target: { value: "program-1" },
    });
    fireEvent.change(screen.getByLabelText("Policy intake term"), {
      target: { value: "term-1" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Load admissions policy" }),
    );

    expect(
      await screen.findByText(
        "No admissions policy exists for this program and intake. Saving creates it.",
      ),
    ).toBeVisible();
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "/api/v1/admissions/policies/program-1/term-1",
    );
    fireEvent.click(screen.getByLabelText("exam"));
    fireEvent.click(screen.getByLabelText("interview"));
    fireEvent.click(
      screen.getByLabelText("A deposit is required to hold a seat"),
    );
    fireEvent.change(screen.getByLabelText("Deposit amount (optional)"), {
      target: { value: "150.00" },
    });
    fireEvent.change(screen.getByLabelText("Deposit currency (optional)"), {
      target: { value: "USD" },
    });
    fireEvent.change(
      screen.getByLabelText(/^Seat reservation duration in seconds/),
      { target: { value: "86400" } },
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Save admissions policy" }),
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [path, options] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(path).toBe("/api/v1/admissions/policies/program-1/term-1");
    expect(options.method).toBe("PUT");
    const headers = new Headers(options.headers);
    expect(headers.get("x-csrf-token")).toBe("csrf-value");
    expect(headers.get("x-organization-id")).toBe("org-1");
    expect(JSON.parse(String(options.body))).toEqual({
      required_stages: ["exam", "interview"],
      deposit_required: true,
      deposit_amount: "150.00",
      deposit_currency: "USD",
      reservation_duration_seconds: 86400,
    });
    expect(await screen.findByText("Admissions policy saved.")).toBeVisible();
  });

  it("creates a quota with a generated identifier and updates an existing one in place", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(async () => notFound())
      .mockImplementationOnce(async (input: RequestInfo | URL) => {
        const path = String(input);
        return json({
          id: path.slice(path.lastIndexOf("/") + 1),
          program_id: "program-1",
          intake_id: "term-1",
          seat_category: "general",
          capacity: 40,
        });
      });
    vi.stubGlobal("fetch", fetchMock);
    renderAdministration();

    fireEvent.change(screen.getByLabelText("Quota program"), {
      target: { value: "program-1" },
    });
    fireEvent.change(screen.getByLabelText("Quota intake term"), {
      target: { value: "term-1" },
    });
    fireEvent.change(screen.getByLabelText("Quota seat category"), {
      target: { value: "general" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Load admission quota" }),
    );

    expect(
      await screen.findByText(
        "No quota exists for this seat category. Saving creates it with a new stable identifier.",
      ),
    ).toBeVisible();
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "/api/v1/admissions/quotas?program_id=program-1&intake_id=term-1&seat_category=general",
    );
    fireEvent.change(screen.getByLabelText("Seat capacity"), {
      target: { value: "40" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Save admission quota" }),
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [path, options] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(path).toMatch(/^\/api\/v1\/admissions\/quotas\/[0-9a-f-]{36}$/);
    expect(options.method).toBe("PUT");
    expect(JSON.parse(String(options.body))).toEqual({
      program_id: "program-1",
      intake_id: "term-1",
      seat_category: "general",
      capacity: 40,
    });
    expect(
      await screen.findByText("Admission quota saved with capacity 40."),
    ).toBeVisible();
    expect(screen.getByText("configured")).toBeVisible();

    fetchMock.mockImplementationOnce(async () =>
      json({
        id: "quota-1",
        program_id: "program-1",
        intake_id: "term-1",
        seat_category: "general",
        capacity: 45,
      }),
    );
    fireEvent.change(screen.getByLabelText("Seat capacity"), {
      target: { value: "45" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Save admission quota" }),
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(fetchMock.mock.calls[2]?.[0]).toBe(path);
    expect(
      await screen.findByText("Admission quota saved with capacity 45."),
    ).toBeVisible();
  });
});
