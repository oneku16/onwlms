const dateInputPattern = /^\d{4}-\d{2}-\d{2}$/;
const timeInputPattern = /^\d{2}:\d{2}(?::\d{2})?$/;

export function textValue(value: FormDataEntryValue | null): string {
  return String(value ?? "").trim();
}

export function optionalTextValue(
  value: FormDataEntryValue | null,
): string | null {
  const text = textValue(value);
  return text === "" ? null : text;
}

/** Return a calendar date exactly as entered (YYYY-MM-DD) or null when invalid. */
export function dateValue(value: FormDataEntryValue | null): string | null {
  const text = textValue(value);
  if (!dateInputPattern.test(text) || Number.isNaN(Date.parse(text))) {
    return null;
  }
  return text;
}

/** Return a wall-clock time (HH:MM or HH:MM:SS) or null when invalid. */
export function timeValue(value: FormDataEntryValue | null): string | null {
  const text = textValue(value);
  return timeInputPattern.test(text) ? text : null;
}

/**
 * Convert a datetime-local input value into an ISO-8601 UTC timestamp using
 * the browser's timezone, or return null when the value is missing or invalid.
 */
export function isoFromDateTimeInput(
  value: FormDataEntryValue | null,
): string | null {
  const text = textValue(value);
  if (!text) {
    return null;
  }
  const parsed = new Date(text);
  return Number.isNaN(parsed.valueOf()) ? null : parsed.toISOString();
}

/** Render an ISO timestamp as a datetime-local value in the browser's timezone. */
export function dateTimeInputFromIso(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) {
    return "";
  }
  const pad = (part: number): string => String(part).padStart(2, "0");
  return `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())}T${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`;
}

export function positiveIntegerValue(
  value: FormDataEntryValue | null,
): number | null {
  const text = textValue(value);
  if (!/^\d+$/.test(text)) {
    return null;
  }
  const parsed = Number(text);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

const decimalPattern = /^\d+(?:\.\d+)?$/;

/** Keep decimal amounts as strings so the backend, not the browser, rounds them. */
export function decimalValue(value: FormDataEntryValue | null): string | null {
  const text = textValue(value);
  return decimalPattern.test(text) ? text : null;
}
