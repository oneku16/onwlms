import {
  asBoolean,
  asNumber,
  asRecord,
  asString,
  unwrapPayload,
  type UnknownRecord,
} from "@/lib/api/validation";

export const applicationStatuses = [
  "draft",
  "submitted",
  "awaiting_exam",
  "awaiting_interview",
  "under_review",
  "waitlisted",
  "accepted",
  "rejected",
  "enrolled",
  "withdrawn",
] as const;

export type ApplicationStatus = (typeof applicationStatuses)[number];

export const applicationSources = [
  "self_submitted",
  "administrator_entered",
] as const;

export const reviewStages = ["document_review", "exam", "interview"] as const;

export type ReviewStage = (typeof reviewStages)[number];

export const reviewOutcomes = [
  "passed",
  "failed",
  "needs_more_information",
] as const;

export const decisionOutcomes = ["accepted", "rejected", "waitlisted"] as const;

export interface ApplicationView {
  readonly id: string;
  readonly applicantProfileId: string;
  readonly programId: string;
  readonly intakeId: string;
  readonly seatCategory: string;
  readonly source: string;
  readonly status: ApplicationStatus;
  readonly depositStatus: string;
  readonly depositRequired: boolean;
  readonly createdAt: string;
  readonly statusChangedAt: string;
}

export interface ReviewView {
  readonly id: string;
  readonly applicationId: string;
  readonly stage: string;
  readonly outcome: string;
  readonly explanation: string | null;
}

export interface ApplicationDocumentView {
  readonly id: string;
  readonly applicationId: string;
  readonly documentType: string;
  readonly fileReference: string;
  readonly mediaType: string;
  readonly sizeBytes: number;
  readonly uploadedAt: string;
}

export interface DecisionView {
  readonly id: string;
  readonly applicationId: string;
  readonly outcome: string;
  readonly reason: string;
  readonly reservationId: string | null;
}

export interface EnrollmentConversionView {
  readonly studentId: string;
  readonly academicEnrollmentId: string;
}

export interface AdmissionsPolicyView {
  readonly programId: string;
  readonly intakeId: string;
  readonly requiredStages: readonly ReviewStage[];
  readonly depositRequired: boolean;
  readonly depositAmount: string | null;
  readonly depositCurrency: string | null;
  readonly reservationDurationSeconds: number;
}

export interface AdmissionQuotaView {
  readonly id: string;
  readonly programId: string;
  readonly intakeId: string;
  readonly seatCategory: string;
  readonly capacity: number;
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

function requireBoolean(
  record: UnknownRecord,
  key: string,
  contract: string,
): boolean {
  const value = asBoolean(record[key]);
  if (value === undefined) {
    throw new Error(`The ${contract} response is not supported.`);
  }
  return value;
}

function requireInteger(
  record: UnknownRecord,
  key: string,
  contract: string,
): number {
  const value = asNumber(record[key]);
  if (value === undefined || !Number.isInteger(value)) {
    throw new Error(`The ${contract} response is not supported.`);
  }
  return value;
}

function isApplicationStatus(value: string): value is ApplicationStatus {
  return applicationStatuses.some((status) => status === value);
}

function isReviewStage(value: string): value is ReviewStage {
  return reviewStages.some((stage) => stage === value);
}

export function parseApplication(value: unknown): ApplicationView {
  const contract = "admissions application";
  const record = requireRecord(value, contract);
  const status = requireString(record, "status", contract);
  if (!isApplicationStatus(status)) {
    throw new Error(`The ${contract} response is not supported.`);
  }
  return {
    id: requireString(record, "id", contract),
    applicantProfileId: requireString(record, "applicant_profile_id", contract),
    programId: requireString(record, "program_id", contract),
    intakeId: requireString(record, "intake_id", contract),
    seatCategory: requireString(record, "seat_category", contract),
    source: requireString(record, "source", contract),
    status,
    depositStatus: requireString(record, "deposit_status", contract),
    depositRequired: requireBoolean(record, "deposit_required", contract),
    createdAt: requireString(record, "created_at", contract),
    statusChangedAt: requireString(record, "status_changed_at", contract),
  };
}

export function parseApplications(value: unknown): readonly ApplicationView[] {
  return requireArray(value, "admissions application").map(parseApplication);
}

export function parseReview(value: unknown): ReviewView {
  const contract = "admissions review";
  const record = requireRecord(value, contract);
  return {
    id: requireString(record, "id", contract),
    applicationId: requireString(record, "application_id", contract),
    stage: requireString(record, "stage", contract),
    outcome: requireString(record, "outcome", contract),
    explanation: requireNullableString(record, "explanation", contract),
  };
}

export function parseReviews(value: unknown): readonly ReviewView[] {
  return requireArray(value, "admissions review").map(parseReview);
}

export function parseApplicationDocument(
  value: unknown,
): ApplicationDocumentView {
  const contract = "application document";
  const record = requireRecord(value, contract);
  return {
    id: requireString(record, "id", contract),
    applicationId: requireString(record, "application_id", contract),
    documentType: requireString(record, "document_type", contract),
    fileReference: requireString(record, "file_reference", contract),
    mediaType: requireString(record, "media_type", contract),
    sizeBytes: requireInteger(record, "size_bytes", contract),
    uploadedAt: requireString(record, "uploaded_at", contract),
  };
}

export function parseApplicationDocuments(
  value: unknown,
): readonly ApplicationDocumentView[] {
  return requireArray(value, "application document").map(
    parseApplicationDocument,
  );
}

export function parseDecision(value: unknown): DecisionView {
  const contract = "admissions decision";
  const record = requireRecord(value, contract);
  return {
    id: requireString(record, "id", contract),
    applicationId: requireString(record, "application_id", contract),
    outcome: requireString(record, "outcome", contract),
    reason: requireString(record, "reason", contract),
    reservationId: requireNullableString(record, "reservation_id", contract),
  };
}

export function parseEnrollmentConversion(
  value: unknown,
): EnrollmentConversionView {
  const contract = "enrollment conversion";
  const record = requireRecord(value, contract);
  return {
    studentId: requireString(record, "student_id", contract),
    academicEnrollmentId: requireString(
      record,
      "academic_enrollment_id",
      contract,
    ),
  };
}

export function parseAdmissionsPolicy(value: unknown): AdmissionsPolicyView {
  const contract = "admissions policy";
  const record = requireRecord(value, contract);
  const stages = record.required_stages ?? [];
  if (!Array.isArray(stages)) {
    throw new Error(`The ${contract} response is not supported.`);
  }
  const requiredStages = stages.map((entry) => {
    const stage = asString(entry);
    if (!stage || !isReviewStage(stage)) {
      throw new Error(`The ${contract} response is not supported.`);
    }
    return stage;
  });
  const depositRequired = asBoolean(record.deposit_required) ?? false;
  return {
    programId: requireString(record, "program_id", contract),
    intakeId: requireString(record, "intake_id", contract),
    requiredStages,
    depositRequired,
    depositAmount: requireNullableString(record, "deposit_amount", contract),
    depositCurrency: requireNullableString(
      record,
      "deposit_currency",
      contract,
    ),
    reservationDurationSeconds: requireInteger(
      record,
      "reservation_duration_seconds",
      contract,
    ),
  };
}

export function parseAdmissionQuota(value: unknown): AdmissionQuotaView {
  const contract = "admission quota";
  const record = requireRecord(value, contract);
  return {
    id: requireString(record, "id", contract),
    programId: requireString(record, "program_id", contract),
    intakeId: requireString(record, "intake_id", contract),
    seatCategory: requireString(record, "seat_category", contract),
    capacity: requireInteger(record, "capacity", contract),
  };
}
