import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { CourseSelectionForm } from "@/components/course-selection-form";
import { EnrollmentApprovals } from "@/components/enrollment-approvals";
import { GradeAmendmentForm } from "@/components/grade-amendment-form";
import { MembershipAdministration } from "@/components/membership-administration";
import { NotificationCenter } from "@/components/notification-center";
import { OrganizationCreateForm } from "@/components/organization-create-form";
import { OrganizationLifecycle } from "@/components/organization-lifecycle";
import { OwnerAppointmentForm } from "@/components/owner-appointment-form";
import {
  EntitlementOverrideForm,
  SubscriptionAssignmentForm,
} from "@/components/platform-entitlement-form";
import { PageHeader } from "@/components/page-header";
import { PlatformAdministration } from "@/components/platform-administration";
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
import { buildCalendarEventsPath } from "@/lib/api/calendar";
import {
  parseMembershipAdministrations,
  parseOwnerLifecycles,
  parsePlatformAdministrators,
  type OwnerLifecycleView,
} from "@/lib/api/administration";
import {
  parseCourseSelectionRequests,
  parseStudentCourseSelectionContext,
} from "@/lib/api/course-selection";
import { ApiError } from "@/lib/api/errors";
import {
  parseAcademicEnrollmentChoices,
  parseGradingScaleChoices,
} from "@/lib/api/grading";
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

function toPageFailure(error: unknown, message: string): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError({ status: 500, code: "page_failed", message });
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
  if (definition.kind === "organization-lifecycle") {
    let organizations: ResourceCollection;
    try {
      organizations = await serverApiRequest(
        "/api/v1/platform/organizations",
        parseResourceCollection,
      );
    } catch (error) {
      const failure = toPageFailure(
        error,
        "Organizations could not be loaded.",
      );
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
        {organizations.items.length === 0 ? (
          <EmptyState message="No organizations have been created yet." />
        ) : (
          <OrganizationLifecycle initialOrganizations={organizations.items} />
        )}
      </>
    );
  }
  if (definition.kind === "owner-appointment") {
    let organizations: ResourceCollection;
    let owners: readonly OwnerLifecycleView[];
    try {
      organizations = await serverApiRequest(
        "/api/v1/platform/organizations",
        parseResourceCollection,
      );
      owners = (
        await Promise.all(
          organizations.items.map((organization) =>
            serverApiRequest(
              `/api/v1/platform/organizations/${encodeURIComponent(organization.id)}/owners`,
              parseOwnerLifecycles,
            ),
          ),
        )
      ).flat();
    } catch (error) {
      const failure = toPageFailure(
        error,
        "Organization owner governance could not be loaded.",
      );
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
        <OwnerAppointmentForm
          initialOwners={owners}
          organizations={organizations.items}
        />
      </>
    );
  }
  if (definition.kind === "subscription-assignment") {
    let organizations: ResourceCollection;
    let plans: ResourceCollection;
    try {
      [organizations, plans] = await Promise.all([
        serverApiRequest(
          "/api/v1/platform/organizations",
          parseResourceCollection,
        ),
        serverApiRequest("/api/v1/platform/plans", parseResourceCollection),
      ]);
    } catch (error) {
      const failure = toPageFailure(
        error,
        "Subscription choices could not be loaded.",
      );
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
        <SubscriptionAssignmentForm
          organizations={organizations.items}
          plans={plans.items}
        />
      </>
    );
  }
  if (definition.kind === "entitlement-override") {
    let organizations: ResourceCollection;
    let features: ResourceCollection;
    try {
      [organizations, features] = await Promise.all([
        serverApiRequest(
          "/api/v1/platform/organizations",
          parseResourceCollection,
        ),
        serverApiRequest("/api/v1/platform/features", parseResourceCollection),
      ]);
    } catch (error) {
      const failure = toPageFailure(
        error,
        "Entitlement choices could not be loaded.",
      );
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
        <EntitlementOverrideForm
          organizations={organizations.items}
          features={features.items}
        />
      </>
    );
  }
  if (definition.kind === "platform-administrators") {
    let administrators;
    try {
      administrators = await serverApiRequest(
        "/api/v1/platform/administrators",
        parsePlatformAdministrators,
      );
    } catch (error) {
      const failure = toPageFailure(
        error,
        "Platform administrators could not be loaded.",
      );
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
        <PlatformAdministration initialAdministrators={administrators} />
      </>
    );
  }
  if (definition.kind === "membership-administration") {
    let memberships;
    try {
      memberships = await serverApiRequest(
        "/api/v1/memberships",
        parseMembershipAdministrations,
        {
          ...(session.activeOrganization
            ? { organizationId: session.activeOrganization.id }
            : {}),
        },
      );
    } catch (error) {
      const failure = toPageFailure(
        error,
        "Organization memberships could not be loaded.",
      );
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
        <MembershipAdministration
          canManage={session.permissions.includes("people.memberships.manage")}
          initialMemberships={memberships}
          organizationId={session.activeOrganization?.id ?? ""}
        />
      </>
    );
  }
  if (definition.kind === "course-selection") {
    let context;
    try {
      context = await serverApiRequest(
        "/api/v1/academics/course-selection-context",
        parseStudentCourseSelectionContext,
        {
          ...(session.activeOrganization
            ? { organizationId: session.activeOrganization.id }
            : {}),
        },
      );
    } catch (error) {
      const failure = toPageFailure(
        error,
        "Course-selection choices could not be loaded.",
      );
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
        <CourseSelectionForm
          canSubmit={session.permissions.includes(
            "academics.course_selection.submit",
          )}
          context={context}
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
    let enrollments;
    let gradingScales;
    let students: ResourceCollection;
    let programs: ResourceCollection;
    let courses: ResourceCollection;
    let terms: ResourceCollection;
    const organizationId = session.activeOrganization?.id ?? "";
    try {
      if (!organizationId) {
        throw new Error("An active organization is required.");
      }
      const requestOptions = { organizationId };
      [enrollments, gradingScales, students, programs, courses, terms] =
        await Promise.all([
          serverApiRequest(
            "/api/v1/academics/student-enrollments?limit=100",
            parseAcademicEnrollmentChoices,
            requestOptions,
          ),
          serverApiRequest(
            "/api/v1/grading/scales?limit=100",
            parseGradingScaleChoices,
            requestOptions,
          ),
          serverApiRequest(
            "/api/v1/organizations/current/students?limit=100",
            parseResourceCollection,
            requestOptions,
          ),
          serverApiRequest(
            "/api/v1/academics/programs?limit=100",
            parseResourceCollection,
            requestOptions,
          ),
          serverApiRequest(
            "/api/v1/academics/courses?limit=100",
            parseResourceCollection,
            requestOptions,
          ),
          serverApiRequest(
            "/api/v1/academics/terms?limit=100",
            parseResourceCollection,
            requestOptions,
          ),
        ]);
    } catch (error) {
      const failure = toPageFailure(
        error,
        "Authorized grade-amendment choices could not be loaded.",
      );
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
        <GradeAmendmentForm
          canReviseClosedTerm={session.permissions.includes(
            "grading.final_grade.revise_closed_term",
          )}
          canSubmit={session.permissions.includes("grading.final_grade.revise")}
          courses={courses.items}
          enrollments={enrollments}
          gradingScales={gradingScales}
          organizationId={organizationId}
          programs={programs.items}
          students={students.items}
          terms={terms.items}
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
    const requestPath =
      definition.kind === "calendar"
        ? buildCalendarEventsPath(new Date())
        : definition.endpoint;
    collection = await serverApiRequest(requestPath, collectionParser, {
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
