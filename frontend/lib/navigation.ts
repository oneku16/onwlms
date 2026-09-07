import type { AccessRule } from "@/lib/access";
import { canAccess } from "@/lib/access";
import type { SessionView } from "@/lib/api/session";

export interface NavigationItem {
  readonly label: string;
  readonly href: string;
  readonly access?: AccessRule;
  readonly unavailable?: boolean;
}

export interface NavigationSection {
  readonly label: string;
  readonly items: readonly NavigationItem[];
}

const organizationAdministrators = [
  "OrganizationOwner",
  "OrganizationAdmin",
] as const;

export const navigationSections: readonly NavigationSection[] = [
  {
    label: "Workspace",
    items: [{ label: "Dashboard", href: "/dashboard" }],
  },
  {
    label: "Platform",
    items: [
      {
        label: "Organizations",
        href: "/platform/organizations",
        access: {
          roles: ["PlatformAdmin"],
          permissions: ["organizations.platform.lifecycle"],
        },
      },
      {
        label: "Create organization",
        href: "/platform/organizations/new",
        access: {
          roles: ["PlatformAdmin"],
          permissions: ["organizations.platform.create"],
        },
      },
      {
        label: "Organization owners",
        href: "/platform/owners",
        access: {
          roles: ["PlatformAdmin"],
          permissions: ["people.platform.appoint_owner"],
        },
      },
      {
        label: "Plans",
        href: "/platform/plans",
        access: {
          roles: ["PlatformAdmin"],
          permissions: ["entitlements.platform.manage"],
        },
      },
      {
        label: "Subscriptions",
        href: "/platform/subscriptions",
        access: {
          roles: ["PlatformAdmin"],
          permissions: ["entitlements.platform.manage"],
        },
      },
      {
        label: "Feature entitlements",
        href: "/platform/entitlements",
        access: {
          roles: ["PlatformAdmin"],
          permissions: ["entitlements.platform.manage"],
        },
      },
      {
        label: "Integration status",
        href: "/platform/integrations",
        access: {
          roles: ["PlatformAdmin"],
          permissions: ["audit.platform.read"],
        },
      },
    ],
  },
  {
    label: "Organization",
    items: (
      [
        ["Campuses", "/organization/campuses", "organizations.campuses.manage"],
        ["Faculties", "/organization/faculties", "academics.structure.manage"],
        [
          "Departments",
          "/organization/departments",
          "academics.structure.manage",
        ],
        ["Programs", "/organization/programs", "academics.curriculum.manage"],
        [
          "Academic calendar",
          "/organization/calendar",
          "academics.structure.manage",
        ],
        ["Terms", "/organization/terms", "academics.structure.manage"],
        [
          "Grading scales",
          "/organization/grading-scales",
          "grading.scale.manage",
        ],
        ["Courses", "/organization/courses", "academics.curriculum.manage"],
        [
          "Groups and cohorts",
          "/organization/groups",
          "academics.structure.manage",
        ],
        ["Rooms", "/organization/rooms", "scheduling.read"],
        ["People", "/organization/people", "people.read"],
        ["Students", "/organization/students", "people.read"],
        ["Teachers", "/organization/teachers", "people.read"],
        ["Staff", "/organization/staff", "people.read"],
        ["Guardians", "/organization/guardians", "people.read"],
        ["Admissions", "/organization/admissions", "admissions.review"],
        [
          "Enrollment approvals",
          "/organization/enrollment-approvals",
          "academics.course_selection.approve",
        ],
        ["Provisioning", "/organization/provisioning", "provisioning.read"],
        ["Branding", "/organization/branding", "organizations.read"],
        ["Audit log", "/organization/audit", "audit.read"],
      ] as const
    ).map(([label, href, permission]) => ({
      label,
      href,
      access: {
        roles: organizationAdministrators,
        permissions: [permission],
        requiresOrganization: true,
      },
    })),
  },
  {
    label: "Integrations",
    items: [
      {
        label: "Moodle status",
        href: "/organization/moodle",
        access: {
          roles: organizationAdministrators,
          permissions: ["integrations.read"],
          entitlements: ["moodle_integration"],
          requiresOrganization: true,
        },
      },
      {
        label: "Roles and permissions",
        href: "/organization/roles",
        access: {
          roles: organizationAdministrators,
          permissions: ["people.memberships.manage"],
          entitlements: ["custom_roles"],
          requiresOrganization: true,
        },
      },
    ],
  },
  {
    label: "Student",
    items: (
      [
        ["Today", "/student/today"],
        ["Full schedule", "/student/schedule"],
        ["Course selection", "/student/course-selection"],
        ["Official grades", "/student/grades"],
        ["GPA and credits", "/student/progress"],
        ["Upcoming events", "/student/events"],
        ["Moodle deadlines", "/student/moodle"],
        ["Profile", "/student/profile"],
        ["Notifications", "/student/notifications"],
      ] as const
    ).map(([label, href]) => ({
      label,
      href,
      access: {
        roles: ["Student"],
        ...(href === "/student/course-selection"
          ? { permissions: ["academics.course_selection.submit"] }
          : {}),
        requiresOrganization: true,
      },
    })),
  },
  {
    label: "Teacher",
    items: (
      [
        ["Teaching schedule", "/teacher/schedule"],
        ["Assigned sections", "/teacher/sections"],
        ["Student lists", "/teacher/students"],
        ["Grade synchronization", "/teacher/grade-sync"],
        ["Grade amendment", "/teacher/grade-amendment"],
        ["Moodle activities", "/teacher/moodle"],
        ["Notifications", "/teacher/notifications"],
      ] as const
    ).map(([label, href]) => ({
      label,
      href,
      access: {
        roles: ["Teacher"],
        requiresOrganization: true,
      },
    })),
  },
  {
    label: "Guardian",
    items: (
      [
        ["Linked students", "/guardian/students", false],
        ["Official grades", "/guardian/grades", false],
        ["Attendance", "/guardian/attendance", true],
        ["Upcoming events", "/guardian/events", false],
        ["Payments", "/guardian/payments", true],
        ["Notifications", "/guardian/notifications", false],
      ] as const
    ).map(([label, href, unavailable]) => ({
      label: `${label}${unavailable ? " — unavailable" : ""}`,
      href,
      unavailable,
      access: {
        roles: ["Guardian"],
        requiresOrganization: true,
      },
    })),
  },
  {
    label: "Permission-based tools",
    items: [
      {
        label: "Organization timetable",
        href: "/organization/timetable",
        access: {
          permissions: ["scheduling.read"],
          requiresOrganization: true,
        },
      },
      {
        label: "Academic workspace",
        href: "/workspace/academics",
        access: {
          permissions: ["academics.structure.manage"],
          requiresOrganization: true,
        },
      },
      {
        label: "Operations workspace",
        href: "/workspace/operations",
        access: {
          permissions: ["provisioning.read"],
          requiresOrganization: true,
        },
      },
    ],
  },
];

export function visibleNavigation(
  session: SessionView,
): readonly NavigationSection[] {
  return navigationSections.flatMap((section) => {
    const items = section.items.filter((item) =>
      canAccess(session, item.access),
    );
    return items.length === 0 ? [] : [{ ...section, items }];
  });
}
