import { describe, expect, it } from "vitest";

import { parseSchedule } from "@/lib/api/schedule";

describe("schedule response contracts", () => {
  it("parses every supported timetable row", () => {
    expect(
      parseSchedule([
        {
          id: "session-1",
          activity_type: "lecture",
          starts_at: "2026-08-10T08:00:00Z",
          ends_at: "2026-08-10T09:00:00Z",
          locked: false,
          version: 2,
        },
      ]),
    ).toEqual([
      expect.objectContaining({
        id: "session-1",
        title: "lecture",
        version: 2,
      }),
    ]);
  });

  it("fails visibly instead of omitting an unsupported timetable row", () => {
    expect(() =>
      parseSchedule([
        {
          id: "session-1",
          starts_at: "2026-08-10T08:00:00Z",
          ends_at: "2026-08-10T09:00:00Z",
          locked: false,
          version: 2,
        },
      ]),
    ).toThrow("The scheduling list response is not supported.");
  });
});
