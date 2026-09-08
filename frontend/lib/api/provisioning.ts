import {
  asNumber,
  asRecord,
  asString,
  unwrapPayload,
  type UnknownRecord,
} from "@/lib/api/validation";

export interface ProvisioningJobView {
  readonly id: string;
  readonly subjectType: string;
  readonly subjectId: string;
  readonly target: string;
  readonly status: string;
  readonly attempts: number;
  readonly createdAt: string;
  readonly updatedAt: string;
  readonly externalReference: string | null;
  readonly lastErrorCode: string | null;
}

/** The backend only accepts retries for jobs still pending or marked retry. */
export const retryableProvisioningStatuses = ["pending", "retry"] as const;

export function isRetryableProvisioningJob(job: ProvisioningJobView): boolean {
  return retryableProvisioningStatuses.some((status) => status === job.status);
}

const contract = "provisioning job";

function requireString(record: UnknownRecord, key: string): string {
  const value = asString(record[key]);
  if (!value) {
    throw new Error(`The ${contract} response is not supported.`);
  }
  return value;
}

function nullableString(record: UnknownRecord, key: string): string | null {
  const value = record[key];
  if (value === null || value === undefined) {
    return null;
  }
  return requireString(record, key);
}

export function parseProvisioningJob(value: unknown): ProvisioningJobView {
  const record = asRecord(unwrapPayload(value));
  const attempts = asNumber(record?.attempts);
  if (!record || attempts === undefined || !Number.isInteger(attempts)) {
    throw new Error(`The ${contract} response is not supported.`);
  }
  return {
    id: requireString(record, "id"),
    subjectType: requireString(record, "subject_type"),
    subjectId: requireString(record, "subject_id"),
    target: requireString(record, "target"),
    status: requireString(record, "status"),
    attempts,
    createdAt: requireString(record, "created_at"),
    updatedAt: requireString(record, "updated_at"),
    externalReference: nullableString(record, "external_reference"),
    lastErrorCode: nullableString(record, "last_error_code"),
  };
}

export function parseProvisioningJobs(
  value: unknown,
): readonly ProvisioningJobView[] {
  const payload = unwrapPayload(value);
  if (!Array.isArray(payload)) {
    throw new Error(`The ${contract} list response is not supported.`);
  }
  return payload.map(parseProvisioningJob);
}
