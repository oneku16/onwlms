import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TimetableBoard } from "@/components/timetable-board";
import type { ScheduleSession } from "@/lib/api/schedule";

const session: ScheduleSession = {
  id: "session-1",
  title: "Discrete Mathematics",
  startsAt: "2026-08-03T08:00:00Z",
  endsAt: "2026-08-03T09:00:00Z",
  version: 4,
  teacher: "Dr. Rivera",
  room: "B-204",
  group: "CS-2028",
};

function dataTransfer(): DataTransfer {
  const store = new Map<string, string>();
  return {
    dropEffect: "none",
    effectAllowed: "all",
    files: [] as unknown as FileList,
    items: [] as unknown as DataTransferItemList,
    types: [],
    clearData: (format?: string) => {
      if (format) {
        store.delete(format);
      } else {
        store.clear();
      }
    },
    getData: (format: string) => store.get(format) ?? "",
    setData: (format: string, value: string) => {
      store.set(format, value);
    },
    setDragImage: () => undefined,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "ownsis_csrf=; Max-Age=0; path=/";
});

describe("TimetableBoard", () => {
  it("omits manual creation when no authoritative activity catalog exists", () => {
    render(
      <TimetableBoard
        canEdit
        initialSessions={[]}
        organizationId="org-1"
        weekStart="2026-08-03"
        timezone="UTC"
      />,
    );

    expect(
      screen.getByRole("heading", {
        name: "Manual session creation is unavailable",
      }),
    ).toBeVisible();
    expect(screen.queryByLabelText("Activity ID")).not.toBeInTheDocument();
    expect(
      screen.queryByLabelText("Course offering ID"),
    ).not.toBeInTheDocument();
  });

  it("persists an HTML5 drag-and-drop move through the scheduling API", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          data: {
            id: session.id,
            title: session.title,
            starts_at: "2026-08-05T11:00:00Z",
            ends_at: "2026-08-05T12:00:00Z",
            locked: false,
            version: 5,
          },
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <TimetableBoard
        canEdit
        initialSessions={[session]}
        organizationId="org-1"
        weekStart="2026-08-03"
        timezone="UTC"
      />,
    );

    const transfer = dataTransfer();
    const original = screen.getByRole("gridcell", {
      name: /Mon Aug 3 at 08:00/i,
    });
    const card = within(original)
      .getByText("Discrete Mathematics")
      .closest("article");
    const target = screen.getByRole("gridcell", {
      name: /Wed Aug 5 at 11:00/i,
    });
    expect(card).not.toBeNull();
    fireEvent.dragStart(card as HTMLElement, { dataTransfer: transfer });
    fireEvent.dragOver(target, { dataTransfer: transfer });
    fireEvent.drop(target, { dataTransfer: transfer });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/v1/scheduling/sessions/session-1");
    expect(options.method).toBe("PATCH");
    expect(options.credentials).toBe("same-origin");
    expect(new Headers(options.headers).get("x-csrf-token")).toBe("csrf-value");
    expect(new Headers(options.headers).get("x-organization-id")).toBe("org-1");
    expect(JSON.parse(String(options.body))).toMatchObject({
      starts_at: "2026-08-05T11:00:00.000Z",
      ends_at: "2026-08-05T12:00:00.000Z",
      version: 4,
    });
    expect(
      await screen.findByText("Discrete Mathematics moved successfully."),
    ).toBeVisible();
    expect(within(target).getByText("Discrete Mathematics")).toBeVisible();
  });

  it("converts an organization-local move to the correct UTC instant", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const bishkekSession: ScheduleSession = {
      ...session,
      startsAt: "2026-08-03T02:00:00Z",
      endsAt: "2026-08-03T03:00:00Z",
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          data: {
            id: session.id,
            title: session.title,
            starts_at: "2026-08-05T05:00:00Z",
            ends_at: "2026-08-05T06:00:00Z",
            locked: false,
            version: 5,
          },
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <TimetableBoard
        canEdit
        initialSessions={[bishkekSession]}
        organizationId="org-1"
        weekStart="2026-08-03"
        timezone="Asia/Bishkek"
      />,
    );

    const transfer = dataTransfer();
    const original = screen.getByRole("gridcell", {
      name: /Mon Aug 3 at 08:00/i,
    });
    const card = within(original)
      .getByText("Discrete Mathematics")
      .closest("article");
    const target = screen.getByRole("gridcell", {
      name: /Wed Aug 5 at 11:00/i,
    });
    fireEvent.dragStart(card as HTMLElement, { dataTransfer: transfer });
    fireEvent.drop(target, { dataTransfer: transfer });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(options.body))).toMatchObject({
      starts_at: "2026-08-05T05:00:00.000Z",
      ends_at: "2026-08-05T06:00:00.000Z",
      version: 4,
    });
    expect(within(target).getByText("Discrete Mathematics")).toBeVisible();
  });

  it("shows hard-conflict feedback and restores the prior slot", async () => {
    document.cookie = "ownsis_csrf=csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: "schedule_conflict",
            message: "The proposed time has hard conflicts.",
            details: {
              conflicts: [
                {
                  code: "room_double_booked",
                  message: "Room B-204 is already booked.",
                },
              ],
            },
          },
        }),
        { status: 409, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <TimetableBoard
        canEdit
        initialSessions={[session]}
        organizationId="org-1"
        weekStart="2026-08-03"
        timezone="UTC"
      />,
    );

    const transfer = dataTransfer();
    const original = screen.getByRole("gridcell", {
      name: /Mon Aug 3 at 08:00/i,
    });
    const card = within(original)
      .getByText("Discrete Mathematics")
      .closest("article");
    const target = screen.getByRole("gridcell", {
      name: /Tue Aug 4 at 09:30/i,
    });
    fireEvent.dragStart(card as HTMLElement, { dataTransfer: transfer });
    fireEvent.drop(target, { dataTransfer: transfer });

    expect(
      await screen.findByText("Room B-204 is already booked."),
    ).toBeVisible();
    expect(within(original).getByText("Discrete Mathematics")).toBeVisible();
    expect(
      within(target).queryByText("Discrete Mathematics"),
    ).not.toBeInTheDocument();
  });
});
