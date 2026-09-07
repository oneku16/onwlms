import { describe, expect, it } from "vitest";

import { buildCalendarEventsPath } from "@/lib/api/calendar";

describe("academic calendar API contract", () => {
  it("supplies the required timezone-aware bounded horizon", () => {
    const path = buildCalendarEventsPath(new Date("2026-08-07T12:00:00.000Z"));
    const url = new URL(path, "https://ownsis.example");

    expect(url.pathname).toBe("/api/v1/academics/calendar-events");
    expect(url.searchParams.get("starts_at")).toBe("2026-02-08T12:00:00.000Z");
    expect(url.searchParams.get("ends_at")).toBe("2027-02-03T12:00:00.000Z");
  });
});
