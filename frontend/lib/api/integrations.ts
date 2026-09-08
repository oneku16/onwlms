import {
  asBoolean,
  asNumber,
  asRecord,
  asString,
  unwrapPayload,
  type UnknownRecord,
} from "@/lib/api/validation";

export interface MoodleStatusView {
  readonly configured: boolean;
  readonly baseUrl: string | null;
  readonly status: string;
  readonly lastSuccessAt: string | null;
  readonly lastErrorCode: string | null;
  readonly gradeEventsConfigured: boolean;
}

export interface GradeEvidenceView {
  readonly id: string;
  readonly externalEventId: string;
  readonly courseOfferingId: string;
  readonly studentPersonId: string;
  readonly gradeValue: string;
  readonly observedAt: string;
  readonly sourceVersion: string;
  readonly status: string;
  readonly reasonCode: string | null;
  readonly receivedAt: string;
  readonly acceptedFinalGradeId: string | null;
  readonly resolvedAt: string | null;
}

export interface ReconciliationRunView {
  readonly id: string;
  readonly termId: string;
  readonly status: string;
  readonly startedAt: string;
  readonly finishedAt: string | null;
  readonly offeringCount: number;
  readonly unmappedOfferingCount: number;
  readonly observedCount: number;
  readonly newEvidenceCount: number;
  readonly duplicateCount: number;
  readonly unmappedUserCount: number;
  readonly errorCode: string | null;
}

function nullableString(record: UnknownRecord, key: string): string | null {
  const value = record[key];
  if (value === null || value === undefined) {
    return null;
  }
  const parsed = asString(value);
  if (parsed === undefined) {
    throw new Error("The Moodle response is not supported.");
  }
  return parsed;
}

/** Parse the credential-free Moodle status; tokens never appear in responses. */
export function parseMoodleStatus(value: unknown): MoodleStatusView {
  const record = asRecord(unwrapPayload(value));
  const configured = asBoolean(record?.configured);
  const status = asString(record?.status);
  if (!record || configured === undefined || !status) {
    throw new Error("The Moodle status response is not supported.");
  }
  return {
    configured,
    baseUrl: nullableString(record, "base_url"),
    status,
    lastSuccessAt: nullableString(record, "last_success_at"),
    lastErrorCode: nullableString(record, "last_error_code"),
    gradeEventsConfigured: asBoolean(record.grade_events_configured) === true,
  };
}

function requiredString(record: UnknownRecord, key: string): string {
  const value = asString(record[key]);
  if (!value) {
    throw new Error("The Moodle grade-evidence response is not supported.");
  }
  return value;
}

function requiredCount(record: UnknownRecord, key: string): number {
  const value = asNumber(record[key]);
  if (value === undefined || !Number.isInteger(value) || value < 0) {
    throw new Error("The reconciliation run response is not supported.");
  }
  return value;
}

/** Parse one stored evidence record; resolver identity is never serialized. */
export function parseGradeEvidence(value: unknown): GradeEvidenceView {
  const record = asRecord(unwrapPayload(value));
  if (!record) {
    throw new Error("The Moodle grade-evidence response is not supported.");
  }
  return {
    id: requiredString(record, "id"),
    externalEventId: requiredString(record, "external_event_id"),
    courseOfferingId: requiredString(record, "course_offering_id"),
    studentPersonId: requiredString(record, "student_person_id"),
    gradeValue: requiredString(record, "grade_value"),
    observedAt: requiredString(record, "observed_at"),
    sourceVersion: requiredString(record, "source_version"),
    status: requiredString(record, "status"),
    reasonCode: nullableString(record, "reason_code"),
    receivedAt: requiredString(record, "received_at"),
    acceptedFinalGradeId: nullableString(record, "accepted_final_grade_id"),
    resolvedAt: nullableString(record, "resolved_at"),
  };
}

export function parseGradeEvidenceList(
  value: unknown,
): readonly GradeEvidenceView[] {
  const payload = unwrapPayload(value);
  if (!Array.isArray(payload)) {
    throw new Error("The Moodle grade-evidence response is not supported.");
  }
  return payload.map(parseGradeEvidence);
}

/** Parse one reconciliation run; counts explain what was and was not observed. */
export function parseReconciliationRun(value: unknown): ReconciliationRunView {
  const record = asRecord(unwrapPayload(value));
  if (!record) {
    throw new Error("The reconciliation run response is not supported.");
  }
  return {
    id: requiredString(record, "id"),
    termId: requiredString(record, "term_id"),
    status: requiredString(record, "status"),
    startedAt: requiredString(record, "started_at"),
    finishedAt: nullableString(record, "finished_at"),
    offeringCount: requiredCount(record, "offering_count"),
    unmappedOfferingCount: requiredCount(record, "unmapped_offering_count"),
    observedCount: requiredCount(record, "observed_count"),
    newEvidenceCount: requiredCount(record, "new_evidence_count"),
    duplicateCount: requiredCount(record, "duplicate_count"),
    unmappedUserCount: requiredCount(record, "unmapped_user_count"),
    errorCode: nullableString(record, "error_code"),
  };
}

export function parseReconciliationRuns(
  value: unknown,
): readonly ReconciliationRunView[] {
  const payload = unwrapPayload(value);
  if (!Array.isArray(payload)) {
    throw new Error("The reconciliation run response is not supported.");
  }
  return payload.map(parseReconciliationRun);
}
