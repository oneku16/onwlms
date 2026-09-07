export type UnknownRecord = Readonly<Record<string, unknown>>;

export function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function asRecord(value: unknown): UnknownRecord | undefined {
  return isRecord(value) ? value : undefined;
}

export function asString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== ""
    ? value.trim()
    : undefined;
}

export function asBoolean(value: unknown): boolean | undefined {
  return typeof value === "boolean" ? value : undefined;
}

export function asNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value)
    ? value
    : undefined;
}

export function asStringArray(value: unknown): readonly string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((entry) => {
    const parsed = asString(entry);
    return parsed === undefined ? [] : [parsed];
  });
}

export function unwrapPayload(value: unknown): unknown {
  const record = asRecord(value);
  return record && "data" in record ? record.data : value;
}

export function readFirstString(
  record: UnknownRecord,
  keys: readonly string[],
): string | undefined {
  for (const key of keys) {
    const parsed = asString(record[key]);
    if (parsed !== undefined) {
      return parsed;
    }
  }
  return undefined;
}

export function normalizeIdentifier(value: string): string {
  return value.trim().toLowerCase().replaceAll("_", ".").replaceAll("-", ".");
}
