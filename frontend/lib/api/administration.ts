import {
  asRecord,
  asString,
  unwrapPayload,
  type UnknownRecord,
} from "@/lib/api/validation";

export const membershipRoles = [
  "organization_owner",
  "organization_admin",
  "student",
  "teacher",
  "guardian",
  "staff",
  "guest",
] as const;

export type MembershipRole = (typeof membershipRoles)[number];
export type MembershipStatus = "active" | "suspended" | "revoked";

export interface MembershipAdministrationView {
  readonly id: string;
  readonly organizationId: string;
  readonly identitySubjectId: string;
  readonly personId: string | null;
  readonly roles: readonly MembershipRole[];
  readonly status: MembershipStatus;
}

export interface PlatformAdministratorView {
  readonly subjectId: string;
  readonly active: boolean;
}

export interface OwnerLifecycleView {
  readonly id: string;
  readonly organizationId: string;
  readonly status: MembershipStatus;
}

function parseNullableString(
  record: UnknownRecord,
  key: string,
): string | null | undefined {
  if (record[key] === null) {
    return null;
  }
  return asString(record[key]);
}

function isMembershipRole(value: string): value is MembershipRole {
  return membershipRoles.some((role) => role === value);
}

function parseMembershipStatus(value: unknown): MembershipStatus | undefined {
  const status = asString(value);
  return status === "active" || status === "suspended" || status === "revoked"
    ? status
    : undefined;
}

export function parseMembershipAdministration(
  value: unknown,
): MembershipAdministrationView {
  const record = asRecord(unwrapPayload(value));
  const id = asString(record?.id);
  const organizationId = asString(record?.organization_id);
  const identitySubjectId = asString(record?.identity_subject_id);
  const personId = record
    ? parseNullableString(record, "person_id")
    : undefined;
  const status = parseMembershipStatus(record?.status);
  const roles = Array.isArray(record?.roles)
    ? record.roles.map(asString)
    : undefined;
  if (
    !record ||
    !id ||
    !organizationId ||
    !identitySubjectId ||
    personId === undefined ||
    !status ||
    !roles ||
    roles.length === 0 ||
    roles.some((role) => role === undefined || !isMembershipRole(role))
  ) {
    throw new Error("The membership administration response is not supported.");
  }
  return {
    id,
    organizationId,
    identitySubjectId,
    personId,
    roles: roles as readonly MembershipRole[],
    status,
  };
}

export function parseMembershipAdministrations(
  value: unknown,
): readonly MembershipAdministrationView[] {
  const payload = unwrapPayload(value);
  if (!Array.isArray(payload)) {
    throw new Error("The membership directory response is not supported.");
  }
  return payload.map(parseMembershipAdministration);
}

export function parseOwnerLifecycle(value: unknown): OwnerLifecycleView {
  const record = asRecord(unwrapPayload(value));
  const id = asString(record?.id);
  const organizationId = asString(record?.organization_id);
  const status = parseMembershipStatus(record?.status);
  if (!record || !id || !organizationId || !status) {
    throw new Error("The organization-owner response is not supported.");
  }
  return { id, organizationId, status };
}

export function parseOwnerLifecycles(
  value: unknown,
): readonly OwnerLifecycleView[] {
  const payload = unwrapPayload(value);
  if (!Array.isArray(payload)) {
    throw new Error("The organization-owner directory is not supported.");
  }
  return payload.map(parseOwnerLifecycle);
}

export function parsePlatformAdministrator(
  value: unknown,
): PlatformAdministratorView {
  const record = asRecord(unwrapPayload(value));
  const subjectId = asString(record?.subject_id);
  if (!record || !subjectId || typeof record.active !== "boolean") {
    throw new Error("The platform-administrator response is not supported.");
  }
  return { subjectId, active: record.active };
}

export function parsePlatformAdministrators(
  value: unknown,
): readonly PlatformAdministratorView[] {
  const payload = unwrapPayload(value);
  if (!Array.isArray(payload)) {
    throw new Error(
      "The platform-administrator directory response is not supported.",
    );
  }
  return payload.map(parsePlatformAdministrator);
}
