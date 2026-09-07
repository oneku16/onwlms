import {
  asNumber,
  asRecord,
  asString,
  readFirstString,
  unwrapPayload,
  type UnknownRecord,
} from "@/lib/api/validation";

export interface ResourceSummary {
  readonly id: string;
  readonly title: string;
  readonly subtitle?: string;
  readonly status?: string;
  readonly code?: string;
  readonly updatedAt?: string;
  readonly occursAt?: string;
}

export interface ResourceCollection {
  readonly items: readonly ResourceSummary[];
  readonly total: number | null;
}

function parseResource(
  record: UnknownRecord,
  index = 0,
): ResourceSummary | undefined {
  const branding = asRecord(record.branding);
  const id =
    readFirstString(record, [
      "id",
      "uid",
      "slug",
      "code",
      "person_id",
      "student_person_id",
      "section_id",
      "external_reference",
      "course_code",
    ]) ?? `summary-${index}`;
  const title =
    readFirstString(record, [
      "display_name",
      "displayName",
      "name",
      "title",
      "subject",
      "section_name",
      "course_title",
    ]) ??
    (branding ? readFirstString(branding, ["display_name"]) : undefined) ??
    (record.gpa !== undefined ? "Official GPA and credits" : undefined) ??
    (record.applicant_profile_id !== undefined &&
    record.program_id !== undefined
      ? `Admissions application ${id.slice(0, 8)}`
      : undefined) ??
    (record.student_academic_enrollment_id !== undefined &&
    Array.isArray(record.offering_ids)
      ? `Course selection ${id.slice(0, 8)}`
      : undefined) ??
    (typeof record.configured === "boolean" && "base_url" in record
      ? "Moodle integration"
      : undefined) ??
    (record.action !== undefined && record.entity_type !== undefined
      ? `${String(record.action)} · ${String(record.entity_type)}`
      : undefined) ??
    (record.target !== undefined && record.subject_type !== undefined
      ? `${String(record.target)} provisioning`
      : undefined) ??
    (record.code !== undefined && record.room_type !== undefined
      ? `${String(record.code)} · ${String(record.room_type)}`
      : undefined) ??
    (record.section_id !== undefined
      ? `Section ${String(record.section_id)}`
      : undefined);
  if (!title) {
    return undefined;
  }
  const gpaSummary =
    record.credits_attempted !== undefined &&
    record.credits_earned !== undefined &&
    record.quality_points !== undefined
      ? [
          `GPA ${asString(record.gpa) ?? "not calculated"}`,
          `${String(record.credits_earned)}/${String(record.credits_attempted)} credits earned`,
          `${String(record.quality_points)} quality points`,
        ].join(" · ")
      : undefined;
  const subtitle =
    gpaSummary ??
    readFirstString(record, [
      "description",
      "type",
      "organization_type",
      "program_name",
      "display_grade",
      "term_name",
      "current_program",
      "institutional_reference",
      "gpa",
      "room_name",
      "seat_category",
      "base_url",
      "requested_credits",
      "entity_id",
      "subject_type",
    ]) ??
    (record.capacity !== undefined
      ? `Capacity ${String(record.capacity)}`
      : undefined) ??
    (record.credits_earned !== undefined
      ? `${String(record.credits_earned)} credits earned`
      : undefined);
  const status =
    readFirstString(record, ["status", "state"]) ??
    (typeof record.is_closed === "boolean"
      ? record.is_closed
        ? "closed"
        : "open"
      : undefined);
  const code = asString(record.code);
  const updatedAt = readFirstString(record, ["updated_at", "updatedAt"]);
  const occursAt = readFirstString(record, [
    "starts_at",
    "due_at",
    "occurred_at",
    "created_at",
  ]);
  return {
    id,
    title,
    ...(subtitle === undefined ? {} : { subtitle }),
    ...(status === undefined ? {} : { status }),
    ...(code === undefined ? {} : { code }),
    ...(updatedAt === undefined ? {} : { updatedAt }),
    ...(occursAt === undefined ? {} : { occursAt }),
  };
}

function findItems(payload: unknown): readonly unknown[] {
  if (Array.isArray(payload)) {
    return payload;
  }
  const record = asRecord(payload);
  if (!record) {
    return [];
  }
  for (const key of ["items", "results", "records", "organizations"]) {
    const candidate = record[key];
    if (Array.isArray(candidate)) {
      return candidate;
    }
  }
  return [record];
}

export function parseResourceCollection(value: unknown): ResourceCollection {
  const payload = unwrapPayload(value);
  const payloadRecord = asRecord(payload);
  const items = findItems(payload).map((entry, index) => {
    const record = asRecord(entry);
    const parsed = record ? parseResource(record, index) : undefined;
    if (!parsed) {
      throw new Error("The resource collection response is not supported.");
    }
    return parsed;
  });
  const total =
    asNumber(payloadRecord?.total) ??
    asNumber(payloadRecord?.count) ??
    (items.length > 0 ? items.length : null);
  return { items, total };
}

export function parseCreatedResource(value: unknown): ResourceSummary {
  const payload = asRecord(unwrapPayload(value));
  const resource = payload ? parseResource(payload) : undefined;
  if (!resource) {
    throw new Error("The created resource response is not supported.");
  }
  return resource;
}

export function parseGuardianGradeCollection(
  value: unknown,
): ResourceCollection {
  const items = findItems(unwrapPayload(value)).flatMap((entry) => {
    const student = asRecord(entry);
    if (!student) {
      throw new Error("The guardian grade response is not supported.");
    }
    const studentId = asString(student.student_person_id);
    const studentName = asString(student.display_name);
    if (
      !studentId ||
      !studentName ||
      !Array.isArray(student.latest_official_grades)
    ) {
      throw new Error("The guardian grade response is not supported.");
    }
    return student.latest_official_grades.map((gradeEntry, index) => {
      const grade = asRecord(gradeEntry);
      const courseCode = asString(grade?.course_code);
      const courseTitle = asString(grade?.course_title);
      const displayGrade = asString(grade?.display_grade);
      const creditsAttempted = asString(grade?.credits_attempted);
      const creditsEarned = asString(grade?.credits_earned);
      if (
        !courseCode ||
        !courseTitle ||
        !displayGrade ||
        !creditsAttempted ||
        !creditsEarned ||
        (grade?.grade_points !== null &&
          asString(grade?.grade_points) === undefined)
      ) {
        throw new Error("The guardian grade response is not supported.");
      }
      const creditSummary = `${creditsEarned}/${creditsAttempted} credits earned`;
      return {
        id: `${studentId}:${courseCode}:${index}`,
        title: `${courseCode} · ${courseTitle}`,
        subtitle: [studentName, creditSummary].filter(Boolean).join(" · "),
        status: displayGrade,
      };
    });
  });
  return { items, total: items.length };
}
