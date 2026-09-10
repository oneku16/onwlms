import type { Metadata } from "next";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { AcademicYearAdministration } from "@/components/academic-year-administration";
import { AdmissionsPolicyAdministration } from "@/components/admissions-policy-administration";
import { AdmissionsWorkflow } from "@/components/admissions-workflow";
import { CalendarAdministration } from "@/components/calendar-administration";
import { CampusAdministration } from "@/components/campus-administration";
import { CohortAdministration } from "@/components/cohort-administration";
import { CourseAdministration } from "@/components/course-administration";
import { CourseOfferingAdministration } from "@/components/course-offering-administration";
import { CourseSelectionForm } from "@/components/course-selection-form";
import { CurriculumAdministration } from "@/components/curriculum-administration";
import { DepartmentAdministration } from "@/components/department-administration";
import { EnrollmentApprovals } from "@/components/enrollment-approvals";
import { FacultyAdministration } from "@/components/faculty-administration";
import { FeatureAdministration } from "@/components/feature-administration";
import { GradeAmendmentForm } from "@/components/grade-amendment-form";
import { GradingScaleAdministration } from "@/components/grading-scale-administration";
import { GuardianAdministration } from "@/components/guardian-administration";
import { MembershipAdministration } from "@/components/membership-administration";
import { GradeEvidenceReview } from "@/components/grade-evidence-review";
import { MoodleIntegration } from "@/components/moodle-integration";
import { NotificationCenter } from "@/components/notification-center";
import { OrganizationBrandingForm } from "@/components/organization-branding-form";
import { OrganizationCreateForm } from "@/components/organization-create-form";
import { OrganizationLifecycle } from "@/components/organization-lifecycle";
import { OwnerAppointmentForm } from "@/components/owner-appointment-form";
import { PeopleAdministration } from "@/components/people-administration";
import { PlanAdministration } from "@/components/plan-administration";
import {
  EntitlementOverrideForm,
  SubscriptionAssignmentForm,
} from "@/components/platform-entitlement-form";
import { SubscriptionLifecycle } from "@/components/subscription-lifecycle";
import { PageHeader } from "@/components/page-header";
import { PlatformAdministration } from "@/components/platform-administration";
import { ProgramAdministration } from "@/components/program-administration";
import { ProvisioningAdministration } from "@/components/provisioning-administration";
import { ResourceList } from "@/components/resource-list";
import { RoomAdministration } from "@/components/room-administration";
import { SelectionPolicyAdministration } from "@/components/selection-policy-administration";
import { StudentEnrollmentAdministration } from "@/components/student-enrollment-administration";
import { TeacherAssignmentAdministration } from "@/components/teacher-assignment-administration";
import { TeacherRosterExplorer } from "@/components/teacher-roster-explorer";
import { TermAdministration } from "@/components/term-administration";
import {
  AccessDenied,
  EmptyState,
  ErrorState,
  UnavailableState,
} from "@/components/states";
import { canAccess } from "@/lib/access";
import {
  parseAcademicYearCollection,
  parseCalendarEventCollection,
  parseCourseOfferings,
  parseStudentEnrollments,
  parseTeacherAssignments,
} from "@/lib/api/academics";
import { parseApplications } from "@/lib/api/admissions";
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
  parseGradingScales,
} from "@/lib/api/grading";
import {
  parseGradeEvidenceList,
  parseMoodleStatus,
  parseReconciliationRuns,
  type GradeEvidenceView,
  type ReconciliationRunView,
} from "@/lib/api/integrations";
import {
  parseNotificationPreferences,
  parseNotifications,
} from "@/lib/api/notifications";
import { parseOrganizationConfiguration } from "@/lib/api/organization";
import { parseFeatures, parsePlans } from "@/lib/api/platform";
import { parseProvisioningJobs } from "@/lib/api/provisioning";
import {
  parseGuardianGradeCollection,
  parseResourceCollection,
  type ResourceCollection,
  type ResourceSummary,
} from "@/lib/api/resources";
import {
  serverApiRequest,
  type ServerApiRequestOptions,
} from "@/lib/api/server";
import { operationalPages, type OperationalPageDefinition } from "@/lib/pages";

interface OperationalRouteProps {
  readonly params: Promise<{ readonly segments: readonly string[] }>;
}

function toPageFailure(error: unknown, message: string): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError({ status: 500, code: "page_failed", message });
}

function failureView(
  header: ReactNode,
  error: unknown,
  message: string,
): ReactNode {
  const failure = toPageFailure(error, message);
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
  const organizationId = session.activeOrganization?.id ?? "";
  const tenantOptions: ServerApiRequestOptions = organizationId
    ? { organizationId }
    : {};
  const hasPermission = (permission: string): boolean =>
    session.permissions.includes(permission);

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
        <SubscriptionLifecycle
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
  if (definition.kind === "plan-administration") {
    let plans;
    try {
      plans = await serverApiRequest(
        "/api/v1/platform/plans?limit=100",
        parsePlans,
      );
    } catch (error) {
      return failureView(header, error, "Plans could not be loaded.");
    }
    return (
      <>
        {header}
        <PlanAdministration initialPlans={plans} />
      </>
    );
  }
  if (definition.kind === "feature-administration") {
    let features;
    try {
      features = await serverApiRequest(
        "/api/v1/platform/features?limit=100",
        parseFeatures,
      );
    } catch (error) {
      return failureView(header, error, "Features could not be loaded.");
    }
    return (
      <>
        {header}
        <FeatureAdministration initialFeatures={features} />
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
  if (definition.kind === "campus-administration") {
    let campuses: ResourceCollection;
    try {
      campuses = await serverApiRequest(
        "/api/v1/campuses",
        parseResourceCollection,
        tenantOptions,
      );
    } catch (error) {
      return failureView(header, error, "Campuses could not be loaded.");
    }
    return (
      <>
        {header}
        <CampusAdministration
          canManage={hasPermission("organizations.campuses.manage")}
          initialCampuses={campuses}
          organizationId={organizationId}
        />
      </>
    );
  }
  if (definition.kind === "faculty-administration") {
    let faculties: ResourceCollection;
    let campuses: ResourceCollection;
    try {
      [faculties, campuses] = await Promise.all([
        serverApiRequest(
          "/api/v1/academics/faculties?limit=100",
          parseResourceCollection,
          tenantOptions,
        ),
        serverApiRequest(
          "/api/v1/campuses",
          parseResourceCollection,
          tenantOptions,
        ),
      ]);
    } catch (error) {
      return failureView(header, error, "Faculties could not be loaded.");
    }
    return (
      <>
        {header}
        <FacultyAdministration
          campuses={campuses.items}
          canManage={hasPermission("academics.structure.manage")}
          initialFaculties={faculties}
          organizationId={organizationId}
        />
      </>
    );
  }
  if (definition.kind === "department-administration") {
    let departments: ResourceCollection;
    let faculties: ResourceCollection;
    try {
      [departments, faculties] = await Promise.all([
        serverApiRequest(
          "/api/v1/academics/departments?limit=100",
          parseResourceCollection,
          tenantOptions,
        ),
        serverApiRequest(
          "/api/v1/academics/faculties?limit=100",
          parseResourceCollection,
          tenantOptions,
        ),
      ]);
    } catch (error) {
      return failureView(header, error, "Departments could not be loaded.");
    }
    return (
      <>
        {header}
        <DepartmentAdministration
          canManage={hasPermission("academics.structure.manage")}
          faculties={faculties.items}
          initialDepartments={departments}
          organizationId={organizationId}
        />
      </>
    );
  }
  if (definition.kind === "program-administration") {
    let programs: ResourceCollection;
    let departments: ResourceCollection;
    try {
      [programs, departments] = await Promise.all([
        serverApiRequest(
          "/api/v1/academics/programs?limit=100",
          parseResourceCollection,
          tenantOptions,
        ),
        serverApiRequest(
          "/api/v1/academics/departments?limit=100",
          parseResourceCollection,
          tenantOptions,
        ),
      ]);
    } catch (error) {
      return failureView(header, error, "Programs could not be loaded.");
    }
    return (
      <>
        {header}
        <ProgramAdministration
          canManage={hasPermission("academics.structure.manage")}
          departments={departments.items}
          initialPrograms={programs}
          organizationId={organizationId}
        />
      </>
    );
  }
  if (definition.kind === "academic-year-administration") {
    let academicYears: ResourceCollection;
    try {
      academicYears = await serverApiRequest(
        "/api/v1/academics/academic-years?limit=100",
        parseAcademicYearCollection,
        tenantOptions,
      );
    } catch (error) {
      return failureView(header, error, "Academic years could not be loaded.");
    }
    return (
      <>
        {header}
        <AcademicYearAdministration
          canManage={hasPermission("academics.structure.manage")}
          initialAcademicYears={academicYears}
          organizationId={organizationId}
        />
      </>
    );
  }
  if (definition.kind === "calendar-administration") {
    let events: ResourceCollection;
    try {
      events = await serverApiRequest(
        buildCalendarEventsPath(new Date()),
        parseCalendarEventCollection,
        tenantOptions,
      );
    } catch (error) {
      return failureView(
        header,
        error,
        "Academic calendar events could not be loaded.",
      );
    }
    return (
      <>
        {header}
        <CalendarAdministration
          canManage={hasPermission("academics.structure.manage")}
          initialEvents={events}
          organizationId={organizationId}
        />
      </>
    );
  }
  if (definition.kind === "term-administration") {
    let terms: ResourceCollection;
    let academicYears: ResourceCollection;
    try {
      [terms, academicYears] = await Promise.all([
        serverApiRequest(
          "/api/v1/academics/terms?limit=100",
          parseResourceCollection,
          tenantOptions,
        ),
        serverApiRequest(
          "/api/v1/academics/academic-years?limit=100",
          parseAcademicYearCollection,
          tenantOptions,
        ),
      ]);
    } catch (error) {
      return failureView(header, error, "Academic terms could not be loaded.");
    }
    return (
      <>
        {header}
        <TermAdministration
          academicYears={academicYears.items}
          canClose={hasPermission("academics.term.close")}
          canManage={hasPermission("academics.structure.manage")}
          initialTerms={terms}
          organizationId={organizationId}
        />
      </>
    );
  }
  if (definition.kind === "curriculum-administration") {
    let programs: ResourceCollection;
    let academicYears: ResourceCollection;
    let courses: ResourceCollection;
    try {
      [programs, academicYears, courses] = await Promise.all([
        serverApiRequest(
          "/api/v1/academics/programs?limit=100",
          parseResourceCollection,
          tenantOptions,
        ),
        serverApiRequest(
          "/api/v1/academics/academic-years?limit=100",
          parseAcademicYearCollection,
          tenantOptions,
        ),
        serverApiRequest(
          "/api/v1/academics/courses?limit=100",
          parseResourceCollection,
          tenantOptions,
        ),
      ]);
    } catch (error) {
      return failureView(
        header,
        error,
        "Curriculum choices could not be loaded.",
      );
    }
    return (
      <>
        {header}
        <CurriculumAdministration
          academicYears={academicYears.items}
          canManage={hasPermission("academics.curriculum.manage")}
          courses={courses.items}
          organizationId={organizationId}
          programs={programs.items}
        />
      </>
    );
  }
  if (definition.kind === "selection-policy-administration") {
    let programs: ResourceCollection;
    let terms: ResourceCollection;
    try {
      [programs, terms] = await Promise.all([
        serverApiRequest(
          "/api/v1/academics/programs?limit=100",
          parseResourceCollection,
          tenantOptions,
        ),
        serverApiRequest(
          "/api/v1/academics/terms?limit=100",
          parseResourceCollection,
          tenantOptions,
        ),
      ]);
    } catch (error) {
      return failureView(
        header,
        error,
        "Course-selection policy choices could not be loaded.",
      );
    }
    return (
      <>
        {header}
        <SelectionPolicyAdministration
          canManage={hasPermission("academics.curriculum.manage")}
          organizationId={organizationId}
          programs={programs.items}
          terms={terms.items}
        />
      </>
    );
  }
  if (definition.kind === "grading-scale-administration") {
    let scales;
    try {
      scales = await serverApiRequest(
        "/api/v1/grading/scales?limit=100",
        parseGradingScales,
        tenantOptions,
      );
    } catch (error) {
      return failureView(header, error, "Grading scales could not be loaded.");
    }
    return (
      <>
        {header}
        <GradingScaleAdministration
          canManage={hasPermission("grading.scale.manage")}
          initialScales={scales}
          organizationId={organizationId}
        />
      </>
    );
  }
  if (definition.kind === "course-administration") {
    let courses: ResourceCollection;
    let departments: ResourceCollection;
    try {
      [courses, departments] = await Promise.all([
        serverApiRequest(
          "/api/v1/academics/courses?limit=100",
          parseResourceCollection,
          tenantOptions,
        ),
        serverApiRequest(
          "/api/v1/academics/departments?limit=100",
          parseResourceCollection,
          tenantOptions,
        ),
      ]);
    } catch (error) {
      return failureView(header, error, "Courses could not be loaded.");
    }
    return (
      <>
        {header}
        <CourseAdministration
          canManage={hasPermission("academics.structure.manage")}
          departments={departments.items}
          initialCourses={courses}
          organizationId={organizationId}
        />
      </>
    );
  }
  if (definition.kind === "course-offering-administration") {
    let offerings;
    let courses: ResourceCollection;
    let terms: ResourceCollection;
    let campuses: ResourceCollection;
    try {
      [offerings, courses, terms, campuses] = await Promise.all([
        serverApiRequest(
          "/api/v1/academics/course-offerings?limit=100",
          parseCourseOfferings,
          tenantOptions,
        ),
        serverApiRequest(
          "/api/v1/academics/courses?limit=100",
          parseResourceCollection,
          tenantOptions,
        ),
        serverApiRequest(
          "/api/v1/academics/terms?limit=100",
          parseResourceCollection,
          tenantOptions,
        ),
        serverApiRequest(
          "/api/v1/campuses",
          parseResourceCollection,
          tenantOptions,
        ),
      ]);
    } catch (error) {
      return failureView(
        header,
        error,
        "Course offerings could not be loaded.",
      );
    }
    return (
      <>
        {header}
        <CourseOfferingAdministration
          campuses={campuses.items}
          canManage={hasPermission("academics.structure.manage")}
          courses={courses.items}
          initialOfferings={offerings}
          organizationId={organizationId}
          terms={terms.items}
        />
      </>
    );
  }
  if (definition.kind === "teacher-assignment-administration") {
    let assignments;
    let offerings;
    let courses: ResourceCollection;
    let terms: ResourceCollection;
    let teachers: ResourceCollection;
    try {
      [assignments, offerings, courses, terms, teachers] = await Promise.all([
        serverApiRequest(
          "/api/v1/academics/teacher-assignments?limit=100",
          parseTeacherAssignments,
          tenantOptions,
        ),
        serverApiRequest(
          "/api/v1/academics/course-offerings?limit=100",
          parseCourseOfferings,
          tenantOptions,
        ),
        serverApiRequest(
          "/api/v1/academics/courses?limit=100",
          parseResourceCollection,
          tenantOptions,
        ),
        serverApiRequest(
          "/api/v1/academics/terms?limit=100",
          parseResourceCollection,
          tenantOptions,
        ),
        serverApiRequest(
          "/api/v1/organizations/current/teachers?limit=100",
          parseResourceCollection,
          tenantOptions,
        ),
      ]);
    } catch (error) {
      return failureView(
        header,
        error,
        "Teacher assignments could not be loaded.",
      );
    }
    return (
      <>
        {header}
        <TeacherAssignmentAdministration
          canManage={hasPermission("academics.structure.manage")}
          courses={courses.items}
          initialAssignments={assignments}
          offerings={offerings}
          organizationId={organizationId}
          teachers={teachers.items}
          terms={terms.items}
        />
      </>
    );
  }
  if (definition.kind === "cohort-administration") {
    let cohorts: ResourceCollection;
    let programs: ResourceCollection;
    let academicYears: ResourceCollection;
    try {
      [cohorts, programs, academicYears] = await Promise.all([
        serverApiRequest(
          "/api/v1/academics/cohorts?limit=100",
          parseResourceCollection,
          tenantOptions,
        ),
        serverApiRequest(
          "/api/v1/academics/programs?limit=100",
          parseResourceCollection,
          tenantOptions,
        ),
        serverApiRequest(
          "/api/v1/academics/academic-years?limit=100",
          parseAcademicYearCollection,
          tenantOptions,
        ),
      ]);
    } catch (error) {
      return failureView(
        header,
        error,
        "Groups and cohorts could not be loaded.",
      );
    }
    return (
      <>
        {header}
        <CohortAdministration
          academicYears={academicYears.items}
          canManage={hasPermission("academics.structure.manage")}
          initialCohorts={cohorts}
          organizationId={organizationId}
          programs={programs.items}
        />
      </>
    );
  }
  if (definition.kind === "room-administration") {
    let rooms: ResourceCollection;
    let campuses: ResourceCollection;
    try {
      [rooms, campuses] = await Promise.all([
        serverApiRequest(
          "/api/v1/academics/rooms?limit=100",
          parseResourceCollection,
          tenantOptions,
        ),
        serverApiRequest(
          "/api/v1/campuses",
          parseResourceCollection,
          tenantOptions,
        ),
      ]);
    } catch (error) {
      return failureView(header, error, "Rooms could not be loaded.");
    }
    return (
      <>
        {header}
        <RoomAdministration
          campuses={campuses.items}
          canManage={hasPermission("academics.structure.manage")}
          initialRooms={rooms}
          organizationId={organizationId}
        />
      </>
    );
  }
  if (definition.kind === "people-administration") {
    let people: ResourceCollection;
    try {
      people = await serverApiRequest(
        "/api/v1/organizations/current/people?limit=100",
        parseResourceCollection,
        tenantOptions,
      );
    } catch (error) {
      return failureView(header, error, "People could not be loaded.");
    }
    return (
      <>
        {header}
        <PeopleAdministration
          canManage={hasPermission("people.manage")}
          initialPeople={people}
          organizationId={organizationId}
        />
      </>
    );
  }
  if (definition.kind === "student-enrollment-administration") {
    let enrollments;
    let students: ResourceCollection;
    let programs: ResourceCollection;
    let academicYears: ResourceCollection;
    let cohorts: ResourceCollection;
    try {
      [enrollments, students, programs, academicYears, cohorts] =
        await Promise.all([
          serverApiRequest(
            "/api/v1/academics/student-enrollments?limit=100",
            parseStudentEnrollments,
            tenantOptions,
          ),
          serverApiRequest(
            "/api/v1/organizations/current/students?limit=100",
            parseResourceCollection,
            tenantOptions,
          ),
          serverApiRequest(
            "/api/v1/academics/programs?limit=100",
            parseResourceCollection,
            tenantOptions,
          ),
          serverApiRequest(
            "/api/v1/academics/academic-years?limit=100",
            parseAcademicYearCollection,
            tenantOptions,
          ),
          serverApiRequest(
            "/api/v1/academics/cohorts?limit=100",
            parseResourceCollection,
            tenantOptions,
          ),
        ]);
    } catch (error) {
      return failureView(
        header,
        error,
        "Student enrollments could not be loaded.",
      );
    }
    return (
      <>
        {header}
        <StudentEnrollmentAdministration
          academicYears={academicYears.items}
          canManage={hasPermission("academics.enrollment.manage")}
          cohorts={cohorts.items}
          initialEnrollments={enrollments}
          organizationId={organizationId}
          programs={programs.items}
          students={students.items}
        />
      </>
    );
  }
  if (definition.kind === "guardian-administration") {
    let guardians: ResourceCollection;
    let students: ResourceCollection;
    try {
      [guardians, students] = await Promise.all([
        serverApiRequest(
          "/api/v1/organizations/current/guardians?limit=100",
          parseResourceCollection,
          tenantOptions,
        ),
        serverApiRequest(
          "/api/v1/organizations/current/students?limit=100",
          parseResourceCollection,
          tenantOptions,
        ),
      ]);
    } catch (error) {
      return failureView(header, error, "Guardians could not be loaded.");
    }
    return (
      <>
        {header}
        <GuardianAdministration
          canManage={hasPermission("people.guardians.manage")}
          initialGuardians={guardians}
          organizationId={organizationId}
          students={students.items}
        />
      </>
    );
  }
  if (definition.kind === "admissions-workflow") {
    let applications;
    let programs: ResourceCollection;
    let terms: ResourceCollection;
    try {
      [applications, programs, terms] = await Promise.all([
        serverApiRequest(
          "/api/v1/admissions/applications?limit=100",
          parseApplications,
          tenantOptions,
        ),
        serverApiRequest(
          "/api/v1/academics/programs?limit=100",
          parseResourceCollection,
          tenantOptions,
        ),
        serverApiRequest(
          "/api/v1/academics/terms?limit=100",
          parseResourceCollection,
          tenantOptions,
        ),
      ]);
    } catch (error) {
      return failureView(
        header,
        error,
        "Admissions applications could not be loaded.",
      );
    }
    return (
      <>
        {header}
        <AdmissionsWorkflow
          canCreate={hasPermission("admissions.application.create")}
          canDecide={hasPermission("admissions.decision.manage")}
          canEnroll={hasPermission("admissions.application.enroll")}
          canManageDocuments={hasPermission("admissions.document.manage")}
          canReview={hasPermission("admissions.review")}
          canSubmit={hasPermission("admissions.application.submit")}
          initialApplications={applications}
          organizationId={organizationId}
          programs={programs.items}
          terms={terms.items}
        />
      </>
    );
  }
  if (definition.kind === "admissions-policy-administration") {
    let programs: ResourceCollection;
    let terms: ResourceCollection;
    try {
      [programs, terms] = await Promise.all([
        serverApiRequest(
          "/api/v1/academics/programs?limit=100",
          parseResourceCollection,
          tenantOptions,
        ),
        serverApiRequest(
          "/api/v1/academics/terms?limit=100",
          parseResourceCollection,
          tenantOptions,
        ),
      ]);
    } catch (error) {
      return failureView(
        header,
        error,
        "Admissions policy choices could not be loaded.",
      );
    }
    return (
      <>
        {header}
        <AdmissionsPolicyAdministration
          canManage={hasPermission("admissions.policy.manage")}
          organizationId={organizationId}
          programs={programs.items}
          terms={terms.items}
        />
      </>
    );
  }
  if (definition.kind === "provisioning-administration") {
    let jobs;
    try {
      jobs = await serverApiRequest(
        "/api/v1/operations/provisioning?limit=100",
        parseProvisioningJobs,
        tenantOptions,
      );
    } catch (error) {
      return failureView(
        header,
        error,
        "Provisioning jobs could not be loaded.",
      );
    }
    return (
      <>
        {header}
        <ProvisioningAdministration
          canRetry={hasPermission("provisioning.retry")}
          initialJobs={jobs}
          organizationId={organizationId}
        />
      </>
    );
  }
  if (definition.kind === "organization-branding") {
    let organization;
    try {
      organization = await serverApiRequest(
        "/api/v1/organization",
        parseOrganizationConfiguration,
        tenantOptions,
      );
    } catch (error) {
      return failureView(
        header,
        error,
        "The organization configuration could not be loaded.",
      );
    }
    return (
      <>
        {header}
        <OrganizationBrandingForm
          canConfigure={hasPermission("organizations.configure")}
          initialOrganization={organization}
          organizationId={organizationId}
        />
      </>
    );
  }
  if (definition.kind === "moodle-integration") {
    const canReadEvidence = hasPermission("integrations.grade_evidence.read");
    let status;
    let evidence: readonly GradeEvidenceView[] = [];
    let runs: readonly ReconciliationRunView[] = [];
    let gradingScales: readonly ResourceSummary[] = [];
    let terms: readonly ResourceSummary[] = [];
    try {
      status = await serverApiRequest(
        "/api/v1/integrations/moodle/status",
        parseMoodleStatus,
        tenantOptions,
      );
      if (canReadEvidence) {
        [evidence, runs] = await Promise.all([
          serverApiRequest(
            "/api/v1/integrations/moodle/grade-evidence?limit=100",
            parseGradeEvidenceList,
            tenantOptions,
          ),
          serverApiRequest(
            "/api/v1/integrations/moodle/grade-reconciliations?limit=20",
            parseReconciliationRuns,
            tenantOptions,
          ),
        ]);
        const [scaleCollection, termCollection] = await Promise.all([
          serverApiRequest(
            "/api/v1/grading/scales?limit=100",
            parseResourceCollection,
            tenantOptions,
          ),
          serverApiRequest(
            "/api/v1/academics/terms?limit=100",
            parseResourceCollection,
            tenantOptions,
          ),
        ]);
        gradingScales = scaleCollection.items;
        terms = termCollection.items;
      }
    } catch (error) {
      return failureView(
        header,
        error,
        "The Moodle integration status could not be loaded.",
      );
    }
    return (
      <>
        {header}
        <MoodleIntegration
          canConfigure={hasPermission("integrations.configure")}
          initialStatus={status}
          organizationId={organizationId}
        />
        {canReadEvidence ? (
          <GradeEvidenceReview
            canReconcile={hasPermission(
              "integrations.grade_evidence.reconcile",
            )}
            canReview={hasPermission("grading.final_grade.record")}
            gradingScales={gradingScales}
            initialEvidence={evidence}
            initialRuns={runs}
            organizationId={organizationId}
            terms={terms}
          />
        ) : null}
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
