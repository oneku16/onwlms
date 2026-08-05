import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { CourseSelectionForm } from "@/components/course-selection-form";
import { EnrollmentApprovals } from "@/components/enrollment-approvals";
import { GradeAmendmentForm } from "@/components/grade-amendment-form";
import { NotificationCenter } from "@/components/notification-center";
import { OrganizationCreateForm } from "@/components/organization-create-form";
import { OwnerAppointmentForm } from "@/components/owner-appointment-form";
import {
  EntitlementOverrideForm,
  SubscriptionAssignmentForm,
} from "@/components/platform-entitlement-form";
import { PageHeader } from "@/components/page-header";
import { ResourceList } from "@/components/resource-list";
import { TeacherRosterExplorer } from "@/components/teacher-roster-explorer";
import { TermAdministration } from "@/components/term-administration";
import {
  AccessDenied,
  EmptyState,
  ErrorState,
  UnavailableState,
} from "@/components/states";
import { canAccess } from "@/lib/access";
import { getSession } from "@/lib/api/auth";
import { parseCourseSelectionRequests } from "@/lib/api/course-selection";
import { ApiError } from "@/lib/api/errors";
import {
  parseNotificationPreferences,
  parseNotifications,
} from "@/lib/api/notifications";
import {
  parseGuardianGradeCollection,
  parseResourceCollection,
  type ResourceCollection,
} from "@/lib/api/resources";
import { serverApiRequest } from "@/lib/api/server";
import { operationalPages, type OperationalPageDefinition } from "@/lib/pages";

interface OperationalRouteProps {
  readonly params: Promise<{ readonly segments: readonly string[] }>;
}

function localDateKey(value: Date, timezone: string): string {
  const parts = new Intl.DateTimeFormat("en", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(value);
  const values = Object.fromEntries(
    parts.map((part) => [part.type, part.value]),
  );
  return `${values.year}-${values.month}-${values.day}`;
}

async function resolveDefinition(
  params: OperationalRouteProps["params"],
): Promise<OperationalPageDefinition | undefined> {
  const { segments } = await params;
  return operationalPages[`/${segments.join("/")}`];
}

export async function generateMetadata({
  params,
}: OperationalRouteProps): Promise<Metadata> {
  const definition = await resolveDefinition(params);
  return { title: definition?.title ?? "Page not found" };
}

export default async function OperationalPage({
  params,
}: OperationalRouteProps) {
  const definition = await resolveDefinition(params);
  if (!definition) {
    notFound();
  }
  const session = await getSession();
  if (!canAccess(session, definition.access)) {
    return <AccessDenied />;
  }

  const header = (
    <PageHeader
      eyebrow={
        session.activeOrganization?.displayName ??
        (session.roles.includes("PlatformAdmin") ? "Platform scope" : "Account")
      }
      title={definition.title}
      description={definition.description}
    />
  );

  if (definition.kind === "unavailable") {
    return (
      <>
        {header}
        <UnavailableState
          reason={
            definition.unavailableReason ?? "This capability is not available."
          }
        />
      </>
    );
  }
  if (definition.kind === "organization-create") {
    return (
      <>
        {header}
        <OrganizationCreateForm />
      </>
    );
  }
  if (definition.kind === "owner-appointment") {
    return (
      <>
        {header}
        <OwnerAppointmentForm />
      </>
    );
  }
  if (definition.kind === "subscription-assignment") {
    return (
      <>
        {header}
        <SubscriptionAssignmentForm />
      </>
    );
  }
  if (definition.kind === "entitlement-override") {
    return (
      <>
        {header}
        <EntitlementOverrideForm />
      </>
    );
  }
  if (definition.kind === "course-selection") {
    return (
      <>
        {header}
        <CourseSelectionForm
          canSubmit={session.permissions.includes(
            "academics.course_selection.submit",
          )}
          organizationId={session.activeOrganization?.id ?? ""}
        />
      </>
    );
  }
  if (definition.kind === "enrollment-approvals") {
    let requests;
    try {
      requests = await serverApiRequest(
        "/api/v1/academics/course-selection-requests?status=pending",
        parseCourseSelectionRequests,
        {
          ...(session.activeOrganization
            ? { organizationId: session.activeOrganization.id }
            : {}),
        },
      );
    } catch (error) {
      const failure =
        error instanceof ApiError
          ? error
          : new ApiError({
              status: 500,
              code: "enrollment_approvals_failed",
              message: "Pending course selections could not be loaded.",
            });
      return (
        <>
          {header}
          <ErrorState
            message={failure.message}
            correlationId={failure.correlationId}
          />
        </>
      );
    }
    return (
      <>
        {header}
        <EnrollmentApprovals
          canDecide={session.permissions.includes(
            "academics.course_selection.approve",
          )}
          initialRequests={requests}
          organizationId={session.activeOrganization?.id ?? ""}
        />
      </>
    );
  }
  if (definition.kind === "grade-amendment") {
    return (
      <>
        {header}
        <GradeAmendmentForm
          canSubmit={session.permissions.includes("grading.final_grade.revise")}
          organizationId={session.activeOrganization?.id ?? ""}
        />
      </>
    );
  }
  if (definition.kind === "notifications") {
    let notifications;
    let preferences;
    try {
      const requestOptions = session.activeOrganization
        ? { organizationId: session.activeOrganization.id }
        : {};
      [notifications, preferences] = await Promise.all([
        serverApiRequest(
          "/api/v1/notifications",
          parseNotifications,
          requestOptions,
        ),
        serverApiRequest(
          "/api/v1/notifications/preferences",
          parseNotificationPreferences,
          requestOptions,
        ),
      ]);
    } catch (error) {
      const failure =
        error instanceof ApiError
          ? error
          : new ApiError({
              status: 500,
              code: "notifications_failed",
              message: "Notifications could not be loaded.",
            });
      return (
        <>
          {header}
          <ErrorState
            message={failure.message}
            correlationId={failure.correlationId}
          />
        </>
      );
    }
    return (
      <>
        {header}
        <NotificationCenter
          canManagePreferences={session.permissions.includes(
            "notifications.preferences.manage_own",
          )}
          canRetry={session.permissions.includes(
            "notifications.delivery.retry_own",
          )}
          initialNotifications={notifications}
          initialPreferences={preferences}
          organizationId={session.activeOrganization?.id ?? ""}
        />
      </>
    );
  }
  if (definition.kind === "teacher-roster") {
    let sections;
    try {
      sections = await serverApiRequest(
        "/api/v1/self-service/teacher/assigned-sections",
        parseResourceCollection,
        {
          ...(session.activeOrganization
            ? { organizationId: session.activeOrganization.id }
            : {}),
        },
      );
    } catch (error) {
      const failure =
        error instanceof ApiError
          ? error
          : new ApiError({
              status: 500,
              code: "teacher_roster_failed",
              message: "Assigned sections could not be loaded.",
            });
      return (
        <>
          {header}
          <ErrorState
            message={failure.message}
            correlationId={failure.correlationId}
          />
        </>
      );
    }
    return (
      <>
        {header}
        <TeacherRosterExplorer
          initialSections={sections}
          organizationId={session.activeOrganization?.id ?? ""}
        />
      </>
    );
  }
  if (definition.kind === "term-administration") {
    let terms;
    try {
      terms = await serverApiRequest(
        "/api/v1/academics/terms",
        parseResourceCollection,
        {
          ...(session.activeOrganization
            ? { organizationId: session.activeOrganization.id }
            : {}),
        },
      );
    } catch (error) {
      const failure =
        error instanceof ApiError
          ? error
          : new ApiError({
              status: 500,
              code: "terms_failed",
              message: "Academic terms could not be loaded.",
            });
      return (
        <>
          {header}
          <ErrorState
            message={failure.message}
            correlationId={failure.correlationId}
          />
        </>
      );
    }
    return (
      <>
        {header}
        <TermAdministration
          canClose={session.permissions.includes("academics.term.close")}
          initialTerms={terms}
          organizationId={session.activeOrganization?.id ?? ""}
        />
      </>
    );
  }
  if (!definition.endpoint) {
    return (
      <>
        {header}
        <ErrorState message="This page has no configured backend capability." />
      </>
    );
  }

  let collection: ResourceCollection;
  try {
    const collectionParser =
      definition.kind === "guardian-grades"
        ? parseGuardianGradeCollection
        : parseResourceCollection;
    collection = await serverApiRequest(definition.endpoint, collectionParser, {
      ...(definition.access?.requiresOrganization && session.activeOrganization
        ? { organizationId: session.activeOrganization.id }
        : {}),
    });
    if (definition.filterToToday) {
      const timezone = session.activeOrganization?.timezone ?? "UTC";
      const today = localDateKey(new Date(), timezone);
      const items = collection.items.filter((item) => {
        if (!item.occursAt) {
          return false;
        }
        const occursAt = new Date(item.occursAt);
        return (
          !Number.isNaN(occursAt.valueOf()) &&
          localDateKey(occursAt, timezone) === today
        );
      });
      collection = { items, total: items.length };
    }
  } catch (error) {
    const failure =
      error instanceof ApiError
        ? error
        : new ApiError({
            status: 500,
            code: "page_failed",
            message: "This page could not be loaded.",
          });
    return (
      <>
        {header}
        <ErrorState
          message={
            failure.status === 404
              ? "The backend capability for this page is not available in the current release. No placeholder records are shown."
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
      {collection.items.length === 0 ? (
        <EmptyState
          message={definition.emptyMessage ?? "No records are available."}
        />
      ) : (
        <ResourceList collection={collection} />
      )}
    </>
  );
}
