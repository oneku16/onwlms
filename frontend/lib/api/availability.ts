import { asRecord, asString, unwrapPayload } from "@/lib/api/validation";

export interface TeacherAvailabilityWindow {
  readonly id: string;
  readonly teacherId: string;
  readonly startsAt: string;
  readonly endsAt: string;
}

export function parseTeacherAvailabilityWindow(
  value: unknown,
): TeacherAvailabilityWindow {
  const record = asRecord(unwrapPayload(value));
  const id = asString(record?.id);
  const teacherId = asString(record?.teacher_id);
  const startsAt = asString(record?.starts_at);
  const endsAt = asString(record?.ends_at);
  if (
    !id ||
    !teacherId ||
    !startsAt ||
    Number.isNaN(Date.parse(startsAt)) ||
    !endsAt ||
    Number.isNaN(Date.parse(endsAt))
  ) {
    throw new Error("The teacher availability response is not supported.");
  }
  return { id, teacherId, startsAt, endsAt };
}

export function parseTeacherAvailability(
  value: unknown,
): readonly TeacherAvailabilityWindow[] {
  const payload = unwrapPayload(value);
  if (!Array.isArray(payload)) {
    throw new Error("The teacher availability list is not supported.");
  }
  return payload.map(parseTeacherAvailabilityWindow);
}

export function parseNoContent(value: unknown): true {
  if (value !== null) {
    throw new Error("The empty response is not supported.");
  }
  return true;
}
