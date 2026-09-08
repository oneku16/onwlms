import type { AccessRule } from "@/lib/access";

export type OperationalPageKind =
  | "collection"
  | "organization-create"
  | "organization-lifecycle"
  | "owner-appointment"
  | "subscription-assignment"
  | "entitlement-override"
  | "platform-administrators"
  | "plan-administration"
  | "feature-administration"
  | "membership-administration"
  | "course-selection"
  | "enrollment-approvals"
  | "grade-amendment"
  | "guardian-grades"
  | "notifications"
  | "teacher-roster"
  | "campus-administration"
  | "faculty-administration"
  | "department-administration"
  | "program-administration"
  | "academic-year-administration"
  | "calendar-administration"
  | "term-administration"
  | "curriculum-administration"
  | "selection-policy-administration"
  | "grading-scale-administration"
  | "course-administration"
  | "course-offering-administration"
  | "teacher-assignment-administration"
  | "cohort-administration"
  | "room-administration"
  | "people-administration"
  | "student-enrollment-administration"
  | "guardian-administration"
  | "admissions-workflow"
  | "admissions-policy-administration"
  | "provisioning-administration"
  | "organization-branding"
  | "moodle-integration"
  | "unavailable";

export interface OperationalPageDefinition {
  readonly title: string;
  readonly description: string;
  readonly endpoint?: `/api/v1/${string}`;
  readonly emptyMessage?: string;
  readonly access?: AccessRule;
  readonly kind?: OperationalPageKind;
  readonly unavailableReason?: string;
  readonly filterToToday?: boolean;
}

const platformAccess = (permission: string): AccessRule => ({
  roles: ["PlatformAdmin"],
  permissions: [permission],
});

const organizationAdminAccess = (permission: string): AccessRule => ({
  roles: ["OrganizationOwner", "OrganizationAdmin"],
  permissions: [permission],
  requiresOrganization: true,
});

const selfAccess = (role: "Student" | "Teacher" | "Guardian"): AccessRule => ({
  roles: [role],
  requiresOrganization: true,
});

export const operationalPages: Readonly<
  Record<string, OperationalPageDefinition>
> = {
  "/platform/organizations": {
    title: "Organizations",
    description:
      "Review tenant lifecycle, institutional type, and current status.",
    endpoint: "/api/v1/platform/organizations",
    emptyMessage: "No organizations have been created yet.",
    kind: "organization-lifecycle",
    access: platformAccess("organizations.platform.lifecycle"),
  },
  "/platform/organizations/new": {
    title: "Create organization",
    description:
      "Create an isolated tenant with its initial institutional settings.",
    kind: "organization-create",
    access: platformAccess("organizations.platform.create"),
  },
  "/platform/owners": {
    title: "Organization owners",
    description:
      "Appoint, recover, suspend, or revoke organization owners through separately authorized platform actions.",
    kind: "owner-appointment",
    access: platformAccess("people.platform.appoint_owner"),
  },
  "/platform/plans": {
    title: "Plans",
    description:
      "Review and create product plans without conflating them with user permissions.",
    endpoint: "/api/v1/platform/plans",
    emptyMessage: "No plans are configured.",
    kind: "plan-administration",
    access: platformAccess("entitlements.platform.manage"),
  },
  "/platform/features": {
    title: "Features",
    description:
      "Register the stable product features that plans and overrides can grant.",
    endpoint: "/api/v1/platform/features",
    emptyMessage: "No features are registered.",
    kind: "feature-administration",
    access: platformAccess("entitlements.platform.manage"),
  },
  "/platform/subscriptions": {
    title: "Subscriptions",
    description: "Assign a plan lifecycle to an organization.",
    kind: "subscription-assignment",
    access: platformAccess("entitlements.platform.manage"),
  },
  "/platform/entitlements": {
    title: "Feature entitlements",
    description:
      "Set an explicit organization feature override and usage limit.",
    kind: "entitlement-override",
    access: platformAccess("entitlements.platform.manage"),
  },
  "/platform/administrators": {
    title: "Platform administrators",
    description:
      "Assign, reactivate, or revoke global governance access without granting tenant academic access.",
    endpoint: "/api/v1/platform/administrators",
    kind: "platform-administrators",
    access: platformAccess("platform_administrators.manage"),
  },
  "/platform/integrations": {
    title: "Integration status",
    description:
      "Monitor tenant-safe integration health without exposing credentials or payloads.",
    kind: "unavailable",
    unavailableReason:
      "Cross-tenant integration inspection is disabled until a governance-only projection can be queried without granting platform administrators tenant academic access.",
    access: platformAccess("audit.platform.read"),
  },
  "/organization/campuses": organizationPage(
    "Campuses",
    "Maintain the campuses owned by the active organization.",
    "/api/v1/campuses",
    "organizations.campuses.manage",
    "campus-administration",
  ),
  "/organization/faculties": organizationPage(
    "Faculties",
    "Review and extend the active organization's faculty structure.",
    "/api/v1/academics/faculties",
    "academics.structure.manage",
    "faculty-administration",
  ),
  "/organization/departments": organizationPage(
    "Departments",
    "Review and create departments within the active organization.",
    "/api/v1/academics/departments",
    "academics.structure.manage",
    "department-administration",
  ),
  "/organization/programs": organizationPage(
    "Programs",
    "Review and create academic programs and their education modes.",
    "/api/v1/academics/programs",
    "academics.structure.manage",
    "program-administration",
  ),
  "/organization/academic-years": organizationPage(
    "Academic years",
    "Review and create the academic years that frame terms, cohorts, and curricula.",
    "/api/v1/academics/academic-years",
    "academics.structure.manage",
    "academic-year-administration",
  ),
  "/organization/calendar": organizationPage(
    "Academic calendar",
    "Review and record organization-wide instructional and closure dates.",
    "/api/v1/academics/calendar-events",
    "academics.structure.manage",
    "calendar-administration",
  ),
  "/organization/terms": organizationPage(
    "Terms and semesters",
    "Create academic periods and apply the audited one-way closure transition.",
    "/api/v1/academics/terms",
    "academics.structure.manage",
    "term-administration",
  ),
  "/organization/curricula": {
    title: "Curricula",
    description:
      "Configure the required and elective courses of a program for an academic year.",
    kind: "curriculum-administration",
    access: organizationAdminAccess("academics.curriculum.manage"),
  },
  "/organization/course-selection-policies": {
    title: "Course-selection policies",
    description:
      "Configure approval, deadline, and credit limits for course selection per program and term.",
    kind: "selection-policy-administration",
    access: organizationAdminAccess("academics.curriculum.manage"),
  },
  "/organization/grading-scales": organizationPage(
    "Grading scales",
    "Review official grading scales and create template copies or custom band mappings.",
    "/api/v1/grading/scales",
    "grading.scale.manage",
    "grading-scale-administration",
  ),
  "/organization/grade-amendments": {
    title: "Grade amendments",
    description:
      "Select an authorized official grade and record an explanation-backed revision without bypassing term closure.",
    kind: "grade-amendment",
    access: organizationAdminAccess("grading.final_grade.revise"),
  },
  "/organization/courses": organizationPage(
    "Courses",
    "Review and create courses with their credit values.",
    "/api/v1/academics/courses",
    "academics.structure.manage",
    "course-administration",
  ),
  "/organization/course-offerings": organizationPage(
    "Course offerings",
    "Review and create term-scoped course sections with meeting windows.",
    "/api/v1/academics/course-offerings",
    "academics.structure.manage",
    "course-offering-administration",
  ),
  "/organization/teacher-assignments": organizationPage(
    "Teacher assignments",
    "Assign tenant teacher profiles to course offerings.",
    "/api/v1/academics/teacher-assignments",
    "academics.structure.manage",
    "teacher-assignment-administration",
  ),
  "/organization/groups": organizationPage(
    "Groups and cohorts",
    "Review and create student groups used by enrollment and scheduling.",
    "/api/v1/academics/cohorts",
    "academics.structure.manage",
    "cohort-administration",
  ),
  "/organization/rooms": organizationPage(
    "Rooms",
    "Review and create rooms with capacity and activity-type suitability.",
    "/api/v1/academics/rooms",
    "academics.structure.manage",
    "room-administration",
  ),
  "/organization/people": organizationPage(
    "People",
    "Review privacy-conscious person summaries and add people or profiles.",
    "/api/v1/organizations/current/people",
    "people.read",
    "people-administration",
  ),
  "/organization/memberships": {
    ...organizationPage(
      "Membership administration",
      "Manage built-in roles and explicit active, suspended, or revoked access state.",
      "/api/v1/memberships",
      "people.memberships.manage",
    ),
    kind: "membership-administration",
  },
  "/organization/students": organizationPage(
    "Students",
    "Review active student memberships and academic profiles.",
    "/api/v1/organizations/current/students",
    "people.read",
  ),
  "/organization/student-enrollments": organizationPage(
    "Student enrollments",
    "Enroll student profiles into programs for an academic year.",
    "/api/v1/academics/student-enrollments",
    "academics.enrollment.manage",
    "student-enrollment-administration",
  ),
  "/organization/teachers": organizationPage(
    "Teachers",
    "Review teacher profiles and current institutional relationships.",
    "/api/v1/organizations/current/teachers",
    "people.read",
  ),
  "/organization/staff": organizationPage(
    "Staff",
    "Review permission-bearing staff memberships.",
    "/api/v1/organizations/current/staff",
    "people.read",
  ),
  "/organization/guardians": organizationPage(
    "Guardians",
    "Review guardian profiles and link them to students.",
    "/api/v1/organizations/current/guardians",
    "people.read",
    "guardian-administration",
  ),
  "/organization/admissions": organizationPage(
    "Admissions",
    "Create, submit, review, and decide applications, then convert accepted applicants.",
    "/api/v1/admissions/applications",
    "admissions.review",
    "admissions-workflow",
  ),
  "/organization/admissions-policies": {
    title: "Admissions policies",
    description:
      "Configure review stages, deposits, reservation windows, and seat quotas per program and intake.",
    kind: "admissions-policy-administration",
    access: organizationAdminAccess("admissions.policy.manage"),
  },
  "/organization/enrollment-approvals": {
    ...organizationPage(
      "Enrollment approvals",
      "Review course-selection requests awaiting an authorized decision.",
      "/api/v1/academics/course-selection-requests?status=pending",
      "academics.course_selection.approve",
    ),
    kind: "enrollment-approvals",
  },
  "/organization/provisioning": organizationPage(
    "Provisioning status",
    "Monitor and retry OwnID, Moodle, Microsoft 365, and notification work.",
    "/api/v1/operations/provisioning",
    "provisioning.read",
    "provisioning-administration",
  ),
  "/organization/branding": organizationPage(
    "Organization branding",
    "Maintain display name, colors, locale, timezone, and domain configuration.",
    "/api/v1/organization",
    "organizations.read",
    "organization-branding",
  ),
  "/organization/audit": organizationPage(
    "Audit log",
    "Review append-only evidence for security-sensitive and official-record changes.",
    "/api/v1/audit",
    "audit.read",
  ),
  "/organization/moodle": {
    ...organizationPage(
      "Moodle integration",
      "Configure Moodle connectivity and review the latest safe status evidence.",
      "/api/v1/integrations/moodle/status",
      "integrations.read",
      "moodle-integration",
    ),
    access: {
      ...organizationAdminAccess("integrations.read"),
      entitlements: ["moodle_integration"],
    },
  },
  "/student/today": {
    ...connectedSelfPage(
      "Today's schedule",
      "See today's confirmed sessions in the active organization's timezone.",
      "/api/v1/self-service/student/schedule",
      "Student",
    ),
    filterToToday: true,
  },
  "/student/schedule": connectedSelfPage(
    "Full schedule",
    "See your confirmed academic schedule.",
    "/api/v1/self-service/student/schedule",
    "Student",
  ),
  "/student/course-selection": {
    title: "Course selection",
    description:
      "Submit your requested course offerings for policy evaluation and any required approval.",
    endpoint: "/api/v1/academics/course-selection-context",
    kind: "course-selection",
    access: {
      ...selfAccess("Student"),
      permissions: ["academics.course_selection.submit"],
    },
  },
  "/student/grades": connectedSelfPage(
    "Official grades",
    "See official OwnSIS results; detailed learning history remains in Moodle.",
    "/api/v1/self-service/student/official-grades",
    "Student",
  ),
  "/student/progress": connectedSelfPage(
    "GPA and credits",
    "Review GPA contribution, credits attempted, and credits earned.",
    "/api/v1/self-service/student/gpa",
    "Student",
  ),
  "/student/events": connectedSelfPage(
    "Upcoming events",
    "Review upcoming academic calendar events.",
    "/api/v1/self-service/student/upcoming-events",
    "Student",
  ),
  "/student/moodle": {
    ...connectedSelfPage(
      "Moodle deadlines",
      "See assignments and deadlines aggregated from Moodle.",
      "/api/v1/self-service/student/moodle-deadlines",
      "Student",
    ),
    access: {
      ...selfAccess("Student"),
      permissions: ["integrations.moodle_deadlines.read_own"],
      entitlements: ["moodle_integration"],
    },
  },
  "/student/profile": connectedSelfPage(
    "Profile",
    "Review your minimum OwnSIS profile identity and institutional reference.",
    "/api/v1/self-service/student/profile",
    "Student",
  ),
  "/student/notifications": {
    ...connectedSelfPage(
      "Notifications",
      "Review messages, delivery status, preferences, and eligible retries.",
      "/api/v1/notifications",
      "Student",
    ),
    kind: "notifications",
  },
  "/teacher/schedule": connectedSelfPage(
    "Teaching schedule",
    "Review your confirmed teaching sessions.",
    "/api/v1/self-service/teacher/schedule",
    "Teacher",
  ),
  "/teacher/sections": connectedSelfPage(
    "Assigned sections",
    "Review the course offerings assigned to you.",
    "/api/v1/self-service/teacher/assigned-sections",
    "Teacher",
  ),
  "/teacher/students": {
    ...connectedSelfPage(
      "Student lists",
      "Select one of your assigned sections and review its minimum authorized roster.",
      "/api/v1/self-service/teacher/assigned-sections",
      "Teacher",
    ),
    kind: "teacher-roster",
  },
  "/teacher/grade-sync": {
    ...connectedSelfPage(
      "Final-grade synchronization",
      "Review Moodle evidence and OwnSIS official-grade synchronization status.",
      "/api/v1/self-service/teacher/grade-synchronization",
      "Teacher",
    ),
    access: {
      ...selfAccess("Teacher"),
      permissions: ["integrations.grade_sync.read_assigned"],
    },
  },
  "/teacher/moodle": {
    ...connectedSelfPage(
      "Upcoming Moodle activities",
      "Review upcoming activities from courses visible to your mapped Moodle account.",
      "/api/v1/self-service/teacher/moodle-deadlines",
      "Teacher",
    ),
    access: {
      ...selfAccess("Teacher"),
      permissions: ["integrations.moodle_deadlines.read_own"],
      entitlements: ["moodle_integration"],
    },
  },
  "/teacher/notifications": {
    ...connectedSelfPage(
      "Notifications",
      "Review messages, delivery status, preferences, and eligible retries.",
      "/api/v1/notifications",
      "Teacher",
    ),
    kind: "notifications",
  },
  "/guardian/students": connectedSelfPage(
    "Linked students",
    "Review students connected through an authorized guardian relationship.",
    "/api/v1/self-service/guardian/linked-students",
    "Guardian",
  ),
  "/guardian/grades": {
    ...connectedSelfPage(
      "Official grades",
      "Review official results for linked students you are authorized to access.",
      "/api/v1/self-service/guardian/linked-students",
      "Guardian",
    ),
    kind: "guardian-grades",
  },
  "/guardian/attendance": unavailablePage(
    "Attendance",
    "Attendance data is not implemented in this release. OwnSIS does not invent attendance summaries.",
    "Guardian",
  ),
  "/guardian/events": connectedSelfPage(
    "Upcoming events",
    "Review upcoming events for linked students.",
    "/api/v1/self-service/guardian/upcoming-events",
    "Guardian",
  ),
  "/guardian/payments": unavailablePage(
    "Payments",
    "Finance is not implemented in this release, so no balances or payment claims are shown.",
    "Guardian",
  ),
  "/guardian/notifications": {
    ...connectedSelfPage(
      "Notifications",
      "Review messages, delivery status, preferences, and eligible retries.",
      "/api/v1/notifications",
      "Guardian",
    ),
    kind: "notifications",
  },
  "/workspace/academics": {
    title: "Academic workspace",
    description:
      "A permission-driven view of academic records available to your staff or guest role.",
    endpoint: "/api/v1/academics/terms",
    emptyMessage: "No academic records are available for your permissions.",
    access: {
      permissions: ["academics.structure.manage"],
      requiresOrganization: true,
    },
  },
  "/workspace/operations": {
    title: "Operations workspace",
    description:
      "A permission-driven view of operational work available to your role.",
    endpoint: "/api/v1/operations/provisioning",
    emptyMessage: "No operational records are available for your permissions.",
    access: { permissions: ["provisioning.read"], requiresOrganization: true },
  },
};

function organizationPage(
  title: string,
  description: string,
  endpoint: `/api/v1/${string}`,
  permission: string,
  kind?: OperationalPageKind,
): OperationalPageDefinition {
  return {
    title,
    description,
    endpoint,
    emptyMessage: `No ${title.toLowerCase()} are available.`,
    access: organizationAdminAccess(permission),
    ...(kind === undefined ? {} : { kind }),
  };
}

function connectedSelfPage(
  title: string,
  description: string,
  endpoint: `/api/v1/${string}`,
  role: "Student" | "Teacher" | "Guardian",
): OperationalPageDefinition {
  return {
    title,
    description,
    endpoint,
    emptyMessage: "Nothing is available here yet.",
    access: selfAccess(role),
  };
}

function unavailablePage(
  title: string,
  reason: string,
  role: "Guardian",
): OperationalPageDefinition {
  return {
    title,
    description: reason,
    kind: "unavailable",
    unavailableReason: reason,
    access: selfAccess(role),
  };
}
