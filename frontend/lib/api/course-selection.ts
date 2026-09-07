import {
  asBoolean,
  asNumber,
  asRecord,
  asString,
  unwrapPayload,
  type UnknownRecord,
} from "@/lib/api/validation";

export interface CourseSelectionMeetingWindow {
  readonly weekday: number;
  readonly startsAt: string;
  readonly endsAt: string;
}

export interface CourseSelectionOfferingOption {
  readonly id: string;
  readonly courseId: string;
  readonly courseCode: string;
  readonly courseTitle: string;
  readonly sectionCode: string;
  readonly credits: string;
  readonly capacity: number;
  readonly meetingWindows: readonly CourseSelectionMeetingWindow[];
}

export interface CourseSelectionTermOption {
  readonly id: string;
  readonly name: string;
  readonly startsOn: string;
  readonly endsOn: string;
  readonly deadline: string;
  readonly maximumCredits: string;
  readonly approvalRequired: boolean;
  readonly offerings: readonly CourseSelectionOfferingOption[];
}

export interface CourseSelectionEnrollmentOption {
  readonly id: string;
  readonly programId: string;
  readonly programName: string;
  readonly academicYearId: string;
  readonly terms: readonly CourseSelectionTermOption[];
}

export interface StudentCourseSelectionContext {
  readonly studentProfileId: string;
  readonly enrollments: readonly CourseSelectionEnrollmentOption[];
}

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

function requireString(record: UnknownRecord, key: string): string {
  const value = asString(record[key]);
  if (!value) {
    throw new Error(`The course-selection ${key} response is not supported.`);
  }
  return value;
}

function parseMeetingWindow(value: unknown): CourseSelectionMeetingWindow {
  const record = asRecord(value);
  const weekday = asNumber(record?.weekday);
  if (!record || weekday === undefined || weekday < 1 || weekday > 7) {
    throw new Error("The course-selection meeting window is not supported.");
  }
  return {
    weekday,
    startsAt: requireString(record, "starts_at"),
    endsAt: requireString(record, "ends_at"),
  };
}

function parseOffering(value: unknown): CourseSelectionOfferingOption {
  const record = asRecord(value);
  const capacity = asNumber(record?.capacity);
  if (
    !record ||
    capacity === undefined ||
    !Array.isArray(record.meeting_windows)
  ) {
    throw new Error("The course-selection offering response is not supported.");
  }
  return {
    id: requireString(record, "id"),
    courseId: requireString(record, "course_id"),
    courseCode: requireString(record, "course_code"),
    courseTitle: requireString(record, "course_title"),
    sectionCode: requireString(record, "section_code"),
    credits: requireString(record, "credits"),
    capacity,
    meetingWindows: record.meeting_windows.map(parseMeetingWindow),
  };
}

function parseTerm(value: unknown): CourseSelectionTermOption {
  const record = asRecord(value);
  const approvalRequired = asBoolean(record?.approval_required);
  if (
    !record ||
    approvalRequired === undefined ||
    !Array.isArray(record.offerings)
  ) {
    throw new Error("The course-selection term response is not supported.");
  }
  return {
    id: requireString(record, "id"),
    name: requireString(record, "name"),
    startsOn: requireString(record, "starts_on"),
    endsOn: requireString(record, "ends_on"),
    deadline: requireString(record, "deadline"),
    maximumCredits: requireString(record, "maximum_credits"),
    approvalRequired,
    offerings: record.offerings.map(parseOffering),
  };
}

function parseEnrollment(value: unknown): CourseSelectionEnrollmentOption {
  const record = asRecord(value);
  if (!record || !Array.isArray(record.terms)) {
    throw new Error(
      "The course-selection enrollment response is not supported.",
    );
  }
  return {
    id: requireString(record, "id"),
    programId: requireString(record, "program_id"),
    programName: requireString(record, "program_name"),
    academicYearId: requireString(record, "academic_year_id"),
    terms: record.terms.map(parseTerm),
  };
}

export function parseStudentCourseSelectionContext(
  value: unknown,
): StudentCourseSelectionContext {
  const record = asRecord(unwrapPayload(value));
  if (!record || !Array.isArray(record.enrollments)) {
    throw new Error("The student course-selection context is not supported.");
  }
  return {
    studentProfileId: requireString(record, "student_profile_id"),
    enrollments: record.enrollments.map(parseEnrollment),
  };
}
