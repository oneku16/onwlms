import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RoomAdministration } from "@/components/room-administration";

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

describe("RoomAdministration", () => {
  it("creates a room with an integer capacity on a selected campus", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "room-1",
          campus_id: "campus-1",
          code: "A-101",
          room_type: "lecture",
          capacity: 40,
        }),
        { status: 201, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <RoomAdministration
        campuses={[{ id: "campus-1", title: "North Valley" }]}
        canManage
        initialRooms={{ items: [], total: 0 }}
        organizationId="org-1"
      />,
    );

    fireEvent.change(screen.getByLabelText("Campus"), {
      target: { value: "campus-1" },
    });
    fireEvent.change(screen.getByLabelText("Room code"), {
      target: { value: "A-101" },
    });
    fireEvent.change(screen.getByLabelText(/^Room type/), {
      target: { value: "lecture" },
    });
    fireEvent.change(screen.getByLabelText("Capacity"), {
      target: { value: "40" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create room" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/academics/rooms");
    expect(options.method).toBe("POST");
    expect(new Headers(options.headers).get("x-csrf-token")).toBe("csrf-value");
    expect(JSON.parse(String(options.body))).toEqual({
      campus_id: "campus-1",
      code: "A-101",
      room_type: "lecture",
      capacity: 40,
    });
    expect(
      await screen.findByText("Room “A-101 · lecture” was created."),
    ).toBeVisible();
  });
});
