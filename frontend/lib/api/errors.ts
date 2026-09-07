import { asRecord, asString, unwrapPayload } from "@/lib/api/validation";

export interface ApiFailure {
  readonly status: number;
  readonly code: string;
  readonly message: string;
  readonly details?: unknown;
  readonly correlationId?: string;
}

export class ApiError extends Error implements ApiFailure {
  readonly status: number;
  readonly code: string;
  readonly details?: unknown;
  readonly correlationId?: string;

  constructor(failure: ApiFailure) {
    super(failure.message);
    this.name = "ApiError";
    this.status = failure.status;
    this.code = failure.code;
    if (failure.details !== undefined) {
      this.details = failure.details;
    }
    if (failure.correlationId !== undefined) {
      this.correlationId = failure.correlationId;
    }
  }
}

export function failureFromPayload(
  status: number,
  value: unknown,
  correlationId?: string,
): ApiFailure {
  const payload = asRecord(unwrapPayload(value));
  const nested = asRecord(payload?.error) ?? payload;
  const code =
    asString(nested?.code) ??
    (status === 403
      ? "forbidden"
      : status === 404
        ? "not_found"
        : status === 409
          ? "conflict"
          : "request_failed");
  const message =
    asString(nested?.message) ??
    asString(nested?.detail) ??
    "The request could not be completed.";
  const details = nested?.details ?? payload?.details;
  return {
    status,
    code,
    message,
    ...(details === undefined ? {} : { details }),
    ...(correlationId === undefined ? {} : { correlationId }),
  };
}
