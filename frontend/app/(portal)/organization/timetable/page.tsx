import { PageHeader } from "@/components/page-header";
import { AccessDenied, ErrorState } from "@/components/states";
import { TeacherAvailabilityPanel } from "@/components/teacher-availability-panel";
import { TimetableBoard } from "@/components/timetable-board";
import { canAccess } from "@/lib/access";
import { getSession } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/errors";
import { parseTeacherAvailability } from "@/lib/api/availability";
import {
  parseResourceCollection,
  type ResourceCollection,
} from "@/lib/api/resources";
import { parseSchedule, type ScheduleSession } from "@/lib/api/schedule";
import { serverApiRequest } from "@/lib/api/server";

export const metadata = { title: "Timetable" };

const timetableAccess = {
  permissions: ["scheduling.read"],
  requiresOrganization: true,
} as const;

function currentDateInTimezone(timezone: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const value = (type: Intl.DateTimeFormatPartTypes): string =>
    parts.find((entry) => entry.type === type)?.value ?? "";
  return `${value("year")}-${value("month")}-${value("day")}`;
}

function mondayFor(dateValue: string): string {
  const date = new Date(`${dateValue}T12:00:00Z`);
  const day = date.getUTCDay();
  const offset = day === 0 ? -6 : 1 - day;
  date.setUTCDate(date.getUTCDate() + offset);
  return date.toISOString().slice(0, 10);
}

export default async function TimetablePage() {
  const session = await getSession();
  if (!canAccess(session, timetableAccess)) {
    return <AccessDenied />;
  }
  const timezone = session.activeOrganization?.timezone ?? "UTC";
  const weekStart = mondayFor(currentDateInTimezone(timezone));
  const header = (
    <PageHeader
      eyebrow={session.activeOrganization?.displayName ?? "Organization"}
      title="Timetable"
      description="Drag a session to another slot or use the keyboard controls. The backend remains authoritative for teacher, room, capacity, group, availability, and calendar conflicts."
    />
  );

  let sessions: readonly ScheduleSession[];
  let availability;
  let teachers: ResourceCollection;
  try {
    const startsAt = `${weekStart}T00:00:00Z`;
    const horizonEnd = new Date(startsAt);
    horizonEnd.setUTCDate(horizonEnd.getUTCDate() + 90);
    [sessions, availability, teachers] = await Promise.all([
      serverApiRequest(
        `/api/v1/scheduling/sessions?week_start=${encodeURIComponent(weekStart)}`,
        parseSchedule,
        { organizationId: session.activeOrganization?.id ?? "" },
      ),
      serverApiRequest(
        `/api/v1/scheduling/teacher-availability?starts_at=${encodeURIComponent(startsAt)}&ends_at=${encodeURIComponent(horizonEnd.toISOString())}`,
        parseTeacherAvailability,
        { organizationId: session.activeOrganization?.id ?? "" },
      ),
      serverApiRequest(
        "/api/v1/organizations/current/teachers?limit=100",
        parseResourceCollection,
        { organizationId: session.activeOrganization?.id ?? "" },
      ),
    ]);
  } catch (error) {
    const failure =
      error instanceof ApiError
        ? error
        : new ApiError({
            status: 500,
            code: "schedule_failed",
            message: "The timetable could not be loaded.",
          });
    return (
      <>
        {header}
        <ErrorState
          message={
            failure.status === 404
              ? "Scheduling is not available in the current backend release."
              : failure.message
          }
          correlationId={failure.correlationId}
        />
      </>
    );
  }

  return (
    <>
      {header}
      <TeacherAvailabilityPanel
        canEdit={session.permissions.includes("scheduling.session.manage")}
        initialWindows={availability}
        organizationId={session.activeOrganization?.id ?? ""}
        teachers={teachers}
        timezone={timezone}
      />
      <TimetableBoard
        canEdit={session.permissions.includes("scheduling.session.manage")}
        initialSessions={sessions}
        organizationId={session.activeOrganization?.id ?? ""}
        weekStart={weekStart}
        timezone={timezone}
      />
    </>
  );
}
