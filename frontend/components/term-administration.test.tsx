import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TermAdministration } from "@/components/term-administration";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

describe("TermAdministration", () => {
  it("closes a selected term with explanation and CSRF protection", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "0198e706-a6d9-7b24-9156-7f92716f5f43",
          name: "Autumn 2026",
          is_closed: true,
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <TermAdministration
        canClose
        organizationId="org-1"
        initialTerms={{
          total: 1,
          items: [
            {
              id: "0198e706-a6d9-7b24-9156-7f92716f5f43",
              title: "Autumn 2026",
              status: "open",
            },
          ],
        }}
      />,
    );

    fireEvent.change(screen.getByLabelText("Term"), {
      target: { value: "0198e706-a6d9-7b24-9156-7f92716f5f43" },
    });
    fireEvent.change(screen.getByLabelText(/^Closure explanation/), {
      target: { value: "Final results have been reviewed." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Close term" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe(
      "/api/v1/academics/terms/0198e706-a6d9-7b24-9156-7f92716f5f43/close",
    );
    expect(options.method).toBe("POST");
    expect(new Headers(options.headers).get("x-csrf-token")).toBe("csrf-value");
    expect(JSON.parse(String(options.body))).toEqual({
      explanation: "Final results have been reviewed.",
    });
    expect(
      await screen.findByText("“Autumn 2026” is now closed."),
    ).toBeVisible();
  });
});
