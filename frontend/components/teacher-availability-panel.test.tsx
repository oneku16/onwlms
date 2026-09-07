import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TeacherAvailabilityPanel } from "@/components/teacher-availability-panel";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

describe("TeacherAvailabilityPanel", () => {
  it("creates an explicit UTC window for a selected tenant teacher", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "window-1",
          teacher_id: "teacher-1",
          starts_at: "2026-08-10T08:00:00Z",
          ends_at: "2026-08-10T16:00:00Z",
        }),
        { status: 201, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <TeacherAvailabilityPanel
        canEdit
        initialWindows={[]}
        organizationId="org-1"
        teachers={{
          total: 1,
          items: [{ id: "teacher-1", title: "Dr. Aitmatova" }],
        }}
        timezone="UTC"
      />,
    );

    fireEvent.click(screen.getByText("Teacher availability"));
    fireEvent.change(screen.getByLabelText("Teacher profile"), {
      target: { value: "teacher-1" },
    });
    fireEvent.change(screen.getByLabelText("Starts at (UTC)"), {
      target: { value: "2026-08-10T08:00" },
    });
    fireEvent.change(screen.getByLabelText("Ends at (UTC)"), {
      target: { value: "2026-08-10T16:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add availability" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/scheduling/teacher-availability");
    expect(options.method).toBe("POST");
    expect(JSON.parse(String(options.body))).toEqual({
      teacher_id: "teacher-1",
      starts_at: "2026-08-10T08:00:00Z",
      ends_at: "2026-08-10T16:00:00Z",
    });
    expect(
      await screen.findByText("Teacher availability saved."),
    ).toBeVisible();
  });
});
