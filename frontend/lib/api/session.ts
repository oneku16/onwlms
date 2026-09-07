import {
  asBoolean,
  asRecord,
  asString,
  asStringArray,
  type UnknownRecord,
} from "@/lib/api/validation";

export const roles = [
  "PlatformAdmin",
  "OrganizationOwner",
  "OrganizationAdmin",
  "Student",
  "Teacher",
  "Guardian",
  "Staff",
  "Guest",
] as const;

export type Role = (typeof roles)[number];

export interface ActorView {
  readonly id: string;
  readonly displayName: string;
  readonly email?: string;
}

export interface CurrentIdentityView {
  readonly actor: ActorView;
  readonly isPlatformAdmin: boolean;
  readonly permissions: readonly string[];
  readonly expiresAt: string;
}

export interface BrandingView {
  readonly primaryColor: string;
  readonly accentColor: string;
  readonly logoUrl?: string;
}

export interface OrganizationView {
  readonly id: string;
  readonly displayName: string;
  readonly slug?: string;
  readonly locale: string;
  readonly timezone: string;
  readonly branding: BrandingView;
}

export interface MembershipDiscoveryView {
  readonly id: string;
  readonly organizationId: string;
  readonly roles: readonly Role[];
  readonly permissions: readonly string[];
}

export interface MembershipView extends MembershipDiscoveryView {
  readonly organization: OrganizationView;
}

export interface SessionView {
  readonly authenticated: boolean;
  readonly actor: ActorView | null;
  readonly activeOrganization: OrganizationView | null;
  readonly memberships: readonly MembershipView[];
  readonly roles: readonly Role[];
  readonly permissions: readonly string[];
  readonly entitlements: readonly string[];
}

export const anonymousSession: SessionView = Object.freeze({
  authenticated: false,
  actor: null,
  activeOrganization: null,
  memberships: [],
  roles: [],
  permissions: [],
  entitlements: [],
});

function requireRecord(value: unknown, contract: string): UnknownRecord {
  const record = asRecord(value);
  if (!record) {
    throw new Error(`Invalid ${contract} response.`);
  }
  return record;
}

function requireString(
  record: UnknownRecord,
  key: string,
  contract: string,
): string {
  const value = asString(record[key]);
  if (!value) {
    throw new Error(`Invalid ${contract} response.`);
  }
  return value;
}

function parseRole(value: string): Role | undefined {
  const compact = value.toLowerCase().replaceAll(/[^a-z]/g, "");
  return roles.find(
    (role) => role.toLowerCase().replaceAll(/[^a-z]/g, "") === compact,
  );
}

function parseRoles(value: unknown): readonly Role[] {
  return [
    ...new Set(
      asStringArray(value).flatMap((entry) => {
        const role = parseRole(entry);
        return role === undefined ? [] : [role];
      }),
    ),
  ];
}

function safeColor(value: unknown, fallback: string): string {
  const parsed = asString(value);
  return parsed && /^#[0-9a-f]{6}$/i.test(parsed) ? parsed : fallback;
}

export function parseCurrentIdentity(value: unknown): CurrentIdentityView {
  const record = requireRecord(value, "identity");
  const id = requireString(record, "id", "identity");
  const displayName = requireString(record, "display_name", "identity");
  const expiresAt = requireString(record, "expires_at", "identity");
  const isPlatformAdmin = asBoolean(record.is_platform_admin);
  if (isPlatformAdmin === undefined) {
    throw new Error("Invalid identity response.");
  }
  if (!Array.isArray(record.permissions)) {
    throw new Error("Invalid identity response.");
  }
  const permissions = asStringArray(record.permissions);
  const email = asString(record.email);
  return {
    actor: {
      id,
      displayName,
      ...(email === undefined ? {} : { email }),
    },
    isPlatformAdmin,
    permissions,
    expiresAt,
  };
}

export function parseMembershipDiscoveries(
  value: unknown,
): readonly MembershipDiscoveryView[] {
  if (!Array.isArray(value)) {
    throw new Error("Invalid memberships response.");
  }
  return value.flatMap((entry) => {
    const record = asRecord(entry);
    if (!record || asString(record.status) !== "active") {
      return [];
    }
    const id = asString(record.id);
    const organizationId = asString(record.organization_id);
    const parsedRoles = parseRoles(record.roles);
    if (!Array.isArray(record.permissions)) {
      throw new Error("Invalid memberships response.");
    }
    const permissions = asStringArray(record.permissions);
    return id && organizationId && parsedRoles.length > 0
      ? [{ id, organizationId, roles: parsedRoles, permissions }]
      : [];
  });
}

export function parseOrganization(value: unknown): OrganizationView {
  const record = requireRecord(value, "organization");
  const branding = requireRecord(record.branding, "organization branding");
  const configuration = requireRecord(
    record.configuration,
    "organization configuration",
  );
  const id = requireString(record, "id", "organization");
  const displayName = requireString(
    branding,
    "display_name",
    "organization branding",
  );
  const slug = asString(record.slug);
  return {
    id,
    displayName,
    locale: asString(configuration.locale) ?? "en",
    timezone: asString(configuration.timezone) ?? "UTC",
    branding: {
      primaryColor: safeColor(branding.primary_color, "#173f5f"),
      accentColor: safeColor(branding.secondary_color, "#f0a43c"),
    },
    ...(slug === undefined ? {} : { slug }),
  };
}

export function parseEntitlement(value: unknown): string | null {
  const record = requireRecord(value, "entitlement");
  const feature = requireString(record, "feature", "entitlement");
  return asBoolean(record.enabled) === true ? feature : null;
}

export function composeSession(
  identity: CurrentIdentityView,
  memberships: readonly MembershipView[],
  activeOrganizationId: string | undefined,
  entitlements: readonly string[],
): SessionView {
  const activeMembership =
    memberships.find(
      (membership) => membership.organizationId === activeOrganizationId,
    ) ?? memberships[0];
  const currentRoles: readonly Role[] = [
    ...new Set([
      ...(identity.isPlatformAdmin ? (["PlatformAdmin"] as const) : []),
      ...(activeMembership?.roles ?? []),
    ]),
  ];
  return {
    authenticated: true,
    actor: identity.actor,
    activeOrganization: activeMembership?.organization ?? null,
    memberships,
    roles: currentRoles,
    permissions: [
      ...new Set([
        ...identity.permissions,
        ...(activeMembership?.permissions ?? []),
      ]),
    ],
    entitlements: [...new Set(entitlements)],
  };
}
