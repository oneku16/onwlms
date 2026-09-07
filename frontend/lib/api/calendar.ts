const calendarWindowDays = 180;
const millisecondsPerDay = 24 * 60 * 60 * 1000;

export function buildCalendarEventsPath(now: Date): string {
  if (Number.isNaN(now.valueOf())) {
    throw new Error("Calendar requests require a valid reference time.");
  }
  const startsAt = new Date(
    now.valueOf() - calendarWindowDays * millisecondsPerDay,
  );
  const endsAt = new Date(
    now.valueOf() + calendarWindowDays * millisecondsPerDay,
  );
  const query = new URLSearchParams({
    starts_at: startsAt.toISOString(),
    ends_at: endsAt.toISOString(),
  });
  return `/api/v1/academics/calendar-events?${query.toString()}`;
}
