import { asRecord, asString, unwrapPayload } from "@/lib/api/validation";

export const profileKinds = [
  "student",
  "staff",
  "teacher",
  "guardian",
] as const;

export type ProfileKind = (typeof profileKinds)[number];

export const contactKinds = ["email", "phone", "telegram"] as const;

export interface ProfileView {
  readonly id: string;
  readonly personId: string;
  readonly kind: ProfileKind;
  readonly title: string | null;
}

export interface GuardianRelationshipView {
  readonly id: string;
  readonly guardianProfileId: string;
  readonly studentProfileId: string;
  readonly relationshipLabel: string;
}

function isProfileKind(value: string): value is ProfileKind {
  return profileKinds.some((kind) => kind === value);
}

/** Parse a created profile; the backend never returns local reference numbers. */
export function parseProfile(value: unknown): ProfileView {
  const record = asRecord(unwrapPayload(value));
  const id = asString(record?.id);
  const personId = asString(record?.person_id);
  const kind = asString(record?.kind);
  const title = record?.title;
  if (
    !record ||
    !id ||
    !personId ||
    !kind ||
    !isProfileKind(kind) ||
    (title !== null && title !== undefined && asString(title) === undefined)
  ) {
    throw new Error("The profile response is not supported.");
  }
  return {
    id,
    personId,
    kind,
    title:
      title === null || title === undefined ? null : (asString(title) ?? null),
  };
}

export function parseGuardianRelationship(
  value: unknown,
): GuardianRelationshipView {
  const record = asRecord(unwrapPayload(value));
  const id = asString(record?.id);
  const guardianProfileId = asString(record?.guardian_profile_id);
  const studentProfileId = asString(record?.student_profile_id);
  const relationshipLabel = asString(record?.relationship_label);
  if (!id || !guardianProfileId || !studentProfileId || !relationshipLabel) {
    throw new Error("The guardian relationship response is not supported.");
  }
  return { id, guardianProfileId, studentProfileId, relationshipLabel };
}
