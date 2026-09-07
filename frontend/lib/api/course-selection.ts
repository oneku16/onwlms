import {
  asRecord,
  asString,
  unwrapPayload,
  type UnknownRecord,
} from "@/lib/api/validation";

export const courseSelectionStatuses = [
  "pending",
  "approved",
  "rejected",
] as const;

export type CourseSelectionStatus = (typeof courseSelectionStatuses)[number];

export interface CourseSelectionRequest {
  readonly id: string;
  readonly studentAcademicEnrollmentId: string;
  readonly termId: string;
  readonly offeringIds: readonly string[];
  readonly requestedCredits: string;
  readonly status: CourseSelectionStatus;
  readonly overrideReason: string | null;
  readonly overriddenRules: readonly string[];
  readonly rejectionReason: string | null;
}

function isStatus(value: string): value is CourseSelectionStatus {
  return courseSelectionStatuses.some((status) => status === value);
}

function parseStringList(
  value: unknown,
  {
    allowEmpty,
    label,
  }: { readonly allowEmpty: boolean; readonly label: string },
): readonly string[] {
  if (!Array.isArray(value) || (!allowEmpty && value.length === 0)) {
    throw new Error(`The ${label} response is not supported.`);
  }
  const parsed = value.map(asString);
  if (parsed.some((item) => item === undefined)) {
    throw new Error(`The ${label} response is not supported.`);
  }
  return parsed as readonly string[];
}

function parseNullableString(
  record: UnknownRecord,
  key: "override_reason" | "rejection_reason",
): string | null {
  const value = record[key];
  if (value === null) {
    return null;
  }
  const parsed = asString(value);
  if (parsed === undefined) {
    throw new Error(`The ${key} response is not supported.`);
  }
  return parsed;
}

export function parseCourseSelectionRequest(
  value: unknown,
): CourseSelectionRequest {
  const record = asRecord(unwrapPayload(value));
  const id = asString(record?.id);
  const studentAcademicEnrollmentId = asString(
    record?.student_academic_enrollment_id,
  );
  const termId = asString(record?.term_id);
  const requestedCredits = asString(record?.requested_credits);
  const status = asString(record?.status);
  if (
    !record ||
    !id ||
    !studentAcademicEnrollmentId ||
    !termId ||
    !requestedCredits ||
    !status ||
    !isStatus(status)
  ) {
    throw new Error("The course-selection response is not supported.");
  }

  return {
    id,
    studentAcademicEnrollmentId,
    termId,
    offeringIds: parseStringList(record.offering_ids, {
      allowEmpty: false,
      label: "course offering identifiers",
    }),
    requestedCredits,
    status,
    overrideReason: parseNullableString(record, "override_reason"),
    overriddenRules: parseStringList(record.overridden_rules, {
      allowEmpty: true,
      label: "overridden rules",
    }),
    rejectionReason: parseNullableString(record, "rejection_reason"),
  };
}

export function parseCourseSelectionRequests(
  value: unknown,
): readonly CourseSelectionRequest[] {
  const payload = unwrapPayload(value);
  if (!Array.isArray(payload)) {
    throw new Error("The course-selection list response is not supported.");
  }
  return payload.map(parseCourseSelectionRequest);
}
