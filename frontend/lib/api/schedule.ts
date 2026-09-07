import {
  asBoolean,
  asNumber,
  asRecord,
  asStringArray,
  readFirstString,
  unwrapPayload,
  type UnknownRecord,
} from "@/lib/api/validation";

export interface ScheduleSession {
  readonly id: string;
  readonly title: string;
  readonly startsAt: string;
  readonly endsAt: string;
  readonly version: number;
  readonly locked?: boolean;
  readonly teacher?: string;
  readonly room?: string;
  readonly group?: string;
}

export interface ScheduleConflict {
  readonly code: string;
  readonly message: string;
}

function validDateTime(value: string | undefined): value is string {
  return value !== undefined && !Number.isNaN(Date.parse(value));
}

function parseScheduleSessionRecord(
  record: UnknownRecord,
): ScheduleSession | undefined {
  const id = readFirstString(record, ["id", "session_id"]);
  const rawTitle = readFirstString(record, [
    "title",
    "course_name",
    "course",
    "subject",
    "activity_type",
  ]);
  const startsAt = readFirstString(record, [
    "starts_at",
    "startsAt",
    "start_time",
  ]);
  const endsAt = readFirstString(record, ["ends_at", "endsAt", "end_time"]);
  const version = asNumber(record.version);
  const locked = asBoolean(record.locked);
  if (
    !id ||
    !rawTitle ||
    !validDateTime(startsAt) ||
    !validDateTime(endsAt) ||
    version === undefined ||
    !Number.isInteger(version) ||
    version < 0 ||
    locked === undefined
  ) {
    return undefined;
  }
  const title = rawTitle.replaceAll("_", " ");
  const teacherIds = asStringArray(record.teacher_ids);
  const groupIds = asStringArray(record.group_ids);
  const roomId = readFirstString(record, ["room_id"]);
  const teacher =
    readFirstString(record, ["teacher_name", "teacher"]) ??
    (teacherIds.length > 0
      ? `${teacherIds.length} ${teacherIds.length === 1 ? "teacher" : "teachers"}`
      : undefined);
  const room =
    readFirstString(record, ["room_name", "room"]) ??
    (roomId ? `Room ${roomId}` : undefined);
  const group =
    readFirstString(record, ["group_name", "group"]) ??
    (groupIds.length > 0
      ? `${groupIds.length} ${groupIds.length === 1 ? "group" : "groups"}`
      : undefined);
  return {
    id,
    title,
    startsAt,
    endsAt,
    version,
    locked,
    ...(teacher === undefined ? {} : { teacher }),
    ...(room === undefined ? {} : { room }),
    ...(group === undefined ? {} : { group }),
  };
}

function scheduleEntries(value: unknown): readonly unknown[] {
  const payload = unwrapPayload(value);
  if (Array.isArray(payload)) {
    return payload;
  }
  const record = asRecord(payload);
  if (!record) {
    throw new Error("The scheduling list response is not supported.");
  }
  for (const key of ["items", "sessions", "lessons", "results"]) {
    if (Array.isArray(record[key])) {
      return record[key];
    }
  }
  throw new Error("The scheduling list response is not supported.");
}

export function parseSchedule(value: unknown): readonly ScheduleSession[] {
  return scheduleEntries(value).map((entry) => {
    const record = asRecord(entry);
    const parsed = record ? parseScheduleSessionRecord(record) : undefined;
    if (!parsed) {
      throw new Error("The scheduling list response is not supported.");
    }
    return parsed;
  });
}

export function parseScheduleSession(value: unknown): ScheduleSession {
  const record = asRecord(unwrapPayload(value));
  const parsed = record ? parseScheduleSessionRecord(record) : undefined;
  if (!parsed) {
    throw new Error("The scheduling response is not supported.");
  }
  return parsed;
}

export function parseScheduleConflicts(
  value: unknown,
): readonly ScheduleConflict[] {
  const unwrapped = unwrapPayload(value);
  const payload = asRecord(unwrapped);
  const details = asRecord(payload?.details) ?? payload;
  const candidates = Array.isArray(unwrapped)
    ? unwrapped
    : Array.isArray(payload?.conflicts)
      ? payload.conflicts
      : details?.conflicts;
  if (!Array.isArray(candidates)) {
    return [];
  }
  return candidates.flatMap((entry) => {
    const record = asRecord(entry);
    if (!record) {
      return [];
    }
    const message = readFirstString(record, ["message", "detail", "reason"]);
    if (!message) {
      return [];
    }
    return [
      {
        code: readFirstString(record, ["code", "type"]) ?? "conflict",
        message,
      },
    ];
  });
}
