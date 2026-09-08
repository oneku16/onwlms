import type { ResourceCollection, ResourceSummary } from "@/lib/api/resources";
import {
  asBoolean,
  asNumber,
  asRecord,
  asString,
  unwrapPayload,
  type UnknownRecord,
} from "@/lib/api/validation";

export const programEducationModes = [
  "fixed_curriculum",
  "flexible_selection",
  "hybrid",
] as const;

export type ProgramEducationMode = (typeof programEducationModes)[number];

export const curriculumCourseKinds = ["required", "elective"] as const;

export type CurriculumCourseKind = (typeof curriculumCourseKinds)[number];

export interface MeetingWindowView {
  /** ISO weekday: 1 is Monday and 7 is Sunday, as the backend contract defines. */
  readonly weekday: number;
  readonly startsAt: string;
  readonly endsAt: string;
}

export interface CourseOfferingView {
  readonly id: string;
  readonly courseId: string;
  readonly termId: string;
  readonly campusId: string;
  readonly sectionCode: string;
  readonly capacity: number;
  readonly meetingWindows: readonly MeetingWindowView[];
}

export interface TeacherAssignmentView {
  readonly id: string;
  readonly courseOfferingId: string;
  readonly teacherId: string;
  readonly role: string;
}

export interface StudentEnrollmentView {
  readonly id: string;
  readonly studentId: string;
  readonly programId: string;
  readonly academicYearId: string;
  readonly cohortId: string | null;
  readonly enrolledAt: string;
  readonly status: string;
}

export interface CurriculumCourseView {
  readonly courseId: string;
  readonly kind: CurriculumCourseKind;
  readonly credits: string;
  readonly prerequisiteCourseIds: readonly string[];
}

export interface CurriculumView {
  readonly id: string;
  readonly programId: string;
  readonly academicYearId: string;
  readonly courses: readonly CurriculumCourseView[];
}

export interface SelectionPolicyView {
  readonly programId: string;
  readonly termId: string;
  readonly approvalRequired: boolean;
  readonly deadline: string;
  readonly educationMode: ProgramEducationMode;
  readonly maximumCredits: string;
}

function requireArray(value: unknown, contract: string): readonly unknown[] {
  const payload = unwrapPayload(value);
  if (!Array.isArray(payload)) {
    throw new Error(`The ${contract} response is not supported.`);
  }
  return payload;
}

function requireRecord(value: unknown, contract: string): UnknownRecord {
  const record = asRecord(unwrapPayload(value));
  if (!record) {
    throw new Error(`The ${contract} response is not supported.`);
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
    throw new Error(`The ${contract} response is not supported.`);
  }
  return value;
}

function requireNullableString(
  record: UnknownRecord,
  key: string,
  contract: string,
): string | null {
  const value = record[key];
  if (value === null || value === undefined) {
    return null;
  }
  return requireString(record, key, contract);
}

function requireStringList(
  value: unknown,
  contract: string,
): readonly string[] {
  if (value === undefined) {
    return [];
  }
  if (!Array.isArray(value)) {
    throw new Error(`The ${contract} response is not supported.`);
  }
  return value.map((entry) => {
    const parsed = asString(entry);
    if (!parsed) {
      throw new Error(`The ${contract} response is not supported.`);
    }
    return parsed;
  });
}

export function isProgramEducationMode(
  value: string,
): value is ProgramEducationMode {
  return programEducationModes.some((mode) => mode === value);
}

function isCurriculumCourseKind(value: string): value is CurriculumCourseKind {
  return curriculumCourseKinds.some((kind) => kind === value);
}

export function parseAcademicYearCollection(
  value: unknown,
): ResourceCollection {
  const contract = "academic year";
  const items = requireArray(value, contract).map((entry): ResourceSummary => {
    const record = requireRecord(entry, contract);
    const startsOn = requireString(record, "starts_on", contract);
    const endsOn = requireString(record, "ends_on", contract);
    return {
      id: requireString(record, "id", contract),
      title: requireString(record, "name", contract),
      subtitle: `${startsOn} – ${endsOn}`,
    };
  });
  return { items, total: items.length };
}

export function parseAcademicYearSummary(value: unknown): ResourceSummary {
  const summary = parseAcademicYearCollection([unwrapPayload(value)]).items[0];
  if (!summary) {
    throw new Error("The academic year response is not supported.");
  }
  return summary;
}

export function parseCalendarEventSummary(value: unknown): ResourceSummary {
  const contract = "calendar event";
  const record = requireRecord(value, contract);
  const instructionAllowed = asBoolean(record.instruction_allowed);
  if (instructionAllowed === undefined) {
    throw new Error(`The ${contract} response is not supported.`);
  }
  const endsAt = requireString(record, "ends_at", contract);
  return {
    id: requireString(record, "id", contract),
    title: requireString(record, "title", contract),
    subtitle: `Ends ${endsAt}`,
    status: instructionAllowed ? "instruction allowed" : "no instruction",
    occursAt: requireString(record, "starts_at", contract),
  };
}

export function parseCalendarEventCollection(
  value: unknown,
): ResourceCollection {
  const items = requireArray(value, "calendar event").map(
    parseCalendarEventSummary,
  );
  return { items, total: items.length };
}

function parseMeetingWindow(value: unknown): MeetingWindowView {
  const contract = "meeting window";
  const record = requireRecord(value, contract);
  const weekday = asNumber(record.weekday);
  if (
    weekday === undefined ||
    !Number.isInteger(weekday) ||
    weekday < 1 ||
    weekday > 7
  ) {
    throw new Error(`The ${contract} response is not supported.`);
  }
  return {
    weekday,
    startsAt: requireString(record, "starts_at", contract),
    endsAt: requireString(record, "ends_at", contract),
  };
}

export function parseCourseOffering(value: unknown): CourseOfferingView {
  const contract = "course offering";
  const record = requireRecord(value, contract);
  const capacity = asNumber(record.capacity);
  const meetingWindows = record.meeting_windows ?? [];
  if (
    capacity === undefined ||
    !Number.isInteger(capacity) ||
    capacity < 1 ||
    !Array.isArray(meetingWindows)
  ) {
    throw new Error(`The ${contract} response is not supported.`);
  }
  return {
    id: requireString(record, "id", contract),
    courseId: requireString(record, "course_id", contract),
    termId: requireString(record, "term_id", contract),
    campusId: requireString(record, "campus_id", contract),
    sectionCode: requireString(record, "section_code", contract),
    capacity,
    meetingWindows: meetingWindows.map(parseMeetingWindow),
  };
}

export function parseCourseOfferings(
  value: unknown,
): readonly CourseOfferingView[] {
  return requireArray(value, "course offering").map(parseCourseOffering);
}

export function parseTeacherAssignment(value: unknown): TeacherAssignmentView {
  const contract = "teacher assignment";
  const record = requireRecord(value, contract);
  return {
    id: requireString(record, "id", contract),
    courseOfferingId: requireString(record, "course_offering_id", contract),
    teacherId: requireString(record, "teacher_id", contract),
    role: requireString(record, "role", contract),
  };
}

export function parseTeacherAssignments(
  value: unknown,
): readonly TeacherAssignmentView[] {
  return requireArray(value, "teacher assignment").map(parseTeacherAssignment);
}

export function parseStudentEnrollment(value: unknown): StudentEnrollmentView {
  const contract = "student enrollment";
  const record = requireRecord(value, contract);
  return {
    id: requireString(record, "id", contract),
    studentId: requireString(record, "student_id", contract),
    programId: requireString(record, "program_id", contract),
    academicYearId: requireString(record, "academic_year_id", contract),
    cohortId: requireNullableString(record, "cohort_id", contract),
    enrolledAt: requireString(record, "enrolled_at", contract),
    status: requireString(record, "status", contract),
  };
}

export function parseStudentEnrollments(
  value: unknown,
): readonly StudentEnrollmentView[] {
  return requireArray(value, "student enrollment").map(parseStudentEnrollment);
}

function parseCurriculumCourse(value: unknown): CurriculumCourseView {
  const contract = "curriculum course";
  const record = requireRecord(value, contract);
  const kind = requireString(record, "kind", contract);
  if (!isCurriculumCourseKind(kind)) {
    throw new Error(`The ${contract} response is not supported.`);
  }
  return {
    courseId: requireString(record, "course_id", contract),
    kind,
    credits: requireString(record, "credits", contract),
    prerequisiteCourseIds: requireStringList(
      record.prerequisite_course_ids,
      contract,
    ),
  };
}

export function parseCurriculum(value: unknown): CurriculumView {
  const contract = "curriculum";
  const record = requireRecord(value, contract);
  if (!Array.isArray(record.courses)) {
    throw new Error(`The ${contract} response is not supported.`);
  }
  return {
    id: requireString(record, "id", contract),
    programId: requireString(record, "program_id", contract),
    academicYearId: requireString(record, "academic_year_id", contract),
    courses: record.courses.map(parseCurriculumCourse),
  };
}

export function parseSelectionPolicy(value: unknown): SelectionPolicyView {
  const contract = "course-selection policy";
  const record = requireRecord(value, contract);
  const approvalRequired = asBoolean(record.approval_required);
  const educationMode = requireString(record, "education_mode", contract);
  if (
    approvalRequired === undefined ||
    !isProgramEducationMode(educationMode)
  ) {
    throw new Error(`The ${contract} response is not supported.`);
  }
  return {
    programId: requireString(record, "program_id", contract),
    termId: requireString(record, "term_id", contract),
    approvalRequired,
    deadline: requireString(record, "deadline", contract),
    educationMode,
    maximumCredits: requireString(record, "maximum_credits", contract),
  };
}
