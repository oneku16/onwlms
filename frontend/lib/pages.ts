import type { AccessRule } from "@/lib/access";

export type OperationalPageKind =
  | "collection"
  | "organization-create"
  | "owner-appointment"
  | "subscription-assignment"
  | "entitlement-override"
  | "course-selection"
  | "enrollment-approvals"
  | "grade-amendment"
  | "guardian-grades"
  | "notifications"
  | "teacher-roster"
  | "term-administration"
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
      "Appoint or recover an organization owner through a separately authorized platform action.",
    kind: "owner-appointment",
    access: platformAccess("people.platform.appoint_owner"),
  },
  "/platform/plans": {
    title: "Plans",
    description:
      "Review available product plans without conflating them with user permissions.",
    endpoint: "/api/v1/platform/plans",
    emptyMessage: "No plans are configured.",
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
  ),
  "/organization/faculties": organizationPage(
    "Faculties",
    "Review the active organization's faculty structure.",
    "/api/v1/academics/faculties",
    "academics.structure.manage",
  ),
  "/organization/departments": organizationPage(
    "Departments",
    "Review departments within the active organization.",
    "/api/v1/academics/departments",
    "academics.structure.manage",
  ),
  "/organization/programs": organizationPage(
    "Programs",
    "Review academic programs and education modes.",
    "/api/v1/academics/programs",
    "academics.curriculum.manage",
  ),
  "/organization/calendar": organizationPage(
    "Academic calendar",
    "Review organization-wide instructional and closure dates.",
    "/api/v1/academics/calendar-events",
    "academics.structure.manage",
  ),
  "/organization/terms": {
    ...organizationPage(
      "Terms and semesters",
      "Review academic periods and apply the audited one-way closure transition.",
      "/api/v1/academics/terms",
      "academics.structure.manage",
    ),
    kind: "term-administration",
  },
  "/organization/grading-scales": organizationPage(
    "Grading scales",
    "Review official grading scales and mappings.",
    "/api/v1/grading/scales",
    "grading.scale.manage",
  ),
  "/organization/courses": organizationPage(
    "Courses",
    "Review courses, credit values, and offering summaries.",
    "/api/v1/academics/courses",
    "academics.curriculum.manage",
  ),
  "/organization/groups": organizationPage(
    "Groups and cohorts",
    "Review student groups used by enrollment and scheduling.",
    "/api/v1/academics/cohorts",
    "academics.structure.manage",
  ),
  "/organization/rooms": organizationPage(
    "Rooms",
    "Review room capacity and activity-type suitability.",
    "/api/v1/academics/rooms",
    "scheduling.read",
  ),
  "/organization/people": organizationPage(
    "People",
    "Review privacy-conscious person summaries for this organization.",
    "/api/v1/organizations/current/people",
    "people.read",
  ),
  "/organization/students": organizationPage(
    "Students",
    "Review active student memberships and academic profiles.",
    "/api/v1/organizations/current/students",
    "people.read",
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
    "Review authorized guardian-to-student relationship summaries.",
    "/api/v1/organizations/current/guardians",
    "people.read",
  ),
  "/organization/admissions": organizationPage(
    "Admissions",
    "Review application lifecycle, decisions, and intake status.",
    "/api/v1/admissions/applications",
    "admissions.review",
  ),
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
    "Monitor retryable OwnID, Moodle, Microsoft 365, and notification work.",
    "/api/v1/operations/provisioning",
    "provisioning.read",
  ),
  "/organization/branding": organizationPage(
    "Organization branding",
    "Review display name, colors, logo metadata, locale, and domain configuration.",
    "/api/v1/organization",
    "organizations.read",
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
      "Review configured Moodle connectivity and the latest safe status evidence.",
      "/api/v1/integrations/moodle/status",
      "integrations.read",
    ),
    access: {
      ...organizationAdminAccess("integrations.read"),
      entitlements: ["moodle_integration"],
    },
  },
  "/organization/roles": {
    ...organizationPage(
      "Roles and permissions",
      "Review tenant-scoped custom authorization policy.",
      "/api/v1/organizations/current/roles",
      "people.memberships.manage",
    ),
    access: {
      ...organizationAdminAccess("people.memberships.manage"),
      entitlements: ["custom_roles"],
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
  "/teacher/grade-sync": connectedSelfPage(
    "Final-grade synchronization",
    "Review Moodle evidence and OwnSIS official-grade synchronization status.",
    "/api/v1/self-service/teacher/grade-synchronization",
    "Teacher",
  ),
  "/teacher/grade-amendment": {
    title: "Grade amendment",
    description:
      "Record an explanation-backed revision only when your membership has explicit official-grade revision permission.",
    kind: "grade-amendment",
    access: selfAccess("Teacher"),
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
): OperationalPageDefinition {
  return {
    title,
    description,
    endpoint,
    emptyMessage: `No ${title.toLowerCase()} are available.`,
    access: organizationAdminAccess(permission),
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
