import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PlatformAdministration } from "@/components/platform-administration";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

describe("PlatformAdministration", () => {
  it("assigns an existing subject without tenant context", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const subjectId = "0198e706-a6d9-7b24-9156-7f92716f5f41";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ subject_id: subjectId, active: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<PlatformAdministration initialAdministrators={[]} />);

    fireEvent.change(
      screen.getByLabelText(/^Existing OwnID subject identifier/),
      { target: { value: subjectId } },
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Assign administrator" }),
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe(`/api/v1/platform/administrators/${subjectId}/assign`);
    const headers = new Headers(options.headers);
    expect(headers.get("x-csrf-token")).toBe("csrf-value");
    expect(headers.get("x-organization-id")).toBeNull();
    expect(await screen.findByText("active")).toBeVisible();
  });
});
