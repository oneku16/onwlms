import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TeacherRosterExplorer } from "@/components/teacher-roster-explorer";

afterEach(() => vi.unstubAllGlobals());

describe("TeacherRosterExplorer", () => {
  it("loads only the selected assigned-section roster", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify([
          {
            person_id: "0198e706-a6d9-7b24-9156-7f92716f5f43",
            display_name: "Aida Sadykova",
            institutional_reference: "STU-2042",
          },
        ]),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <TeacherRosterExplorer
        organizationId="org-1"
        initialSections={{
          total: 1,
          items: [
            {
              id: "0198e706-a6d9-7b24-9156-7f92716f5f99",
              title: "CS-101 / A",
              subtitle: "Autumn 2026",
            },
          ],
        }}
      />,
    );

    fireEvent.change(screen.getByLabelText("Assigned section"), {
      target: { value: "0198e706-a6d9-7b24-9156-7f92716f5f99" },
    });
    fireEvent.click(screen.getByRole("button", { name: "View student list" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "/api/v1/self-service/teacher/assigned-sections/0198e706-a6d9-7b24-9156-7f92716f5f99/students",
    );
    expect(await screen.findByText("Aida Sadykova")).toBeVisible();
    expect(screen.getByText("STU-2042")).toBeVisible();
  });
});
