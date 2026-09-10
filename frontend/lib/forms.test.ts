import { describe, expect, it } from "vitest";

import {
  dateTimeInputFromIso,
  dateValue,
  decimalValue,
  isoFromDateTimeInput,
  optionalTextValue,
  positiveIntegerValue,
  timeValue,
} from "@/lib/forms";

describe("form value helpers", () => {
  it("keeps calendar dates exactly as entered and rejects malformed values", () => {
    expect(dateValue("2026-09-01")).toBe("2026-09-01");
    expect(dateValue("09/01/2026")).toBeNull();
    expect(dateValue("")).toBeNull();
  });

  it("accepts wall-clock times only", () => {
    expect(timeValue("08:30")).toBe("08:30");
    expect(timeValue("08:30:00")).toBe("08:30:00");
    expect(timeValue("8am")).toBeNull();
  });

  it("round-trips datetime-local values through ISO timestamps", () => {
    const iso = isoFromDateTimeInput("2026-08-30T18:00");
    expect(iso).not.toBeNull();
    expect(Date.parse(String(iso))).not.toBeNaN();
    expect(isoFromDateTimeInput(dateTimeInputFromIso(String(iso)))).toBe(iso);
    expect(isoFromDateTimeInput("not a date")).toBeNull();
    expect(isoFromDateTimeInput(null)).toBeNull();
    expect(dateTimeInputFromIso("invalid")).toBe("");
  });

  it("parses positive integers and decimal strings without rounding", () => {
    expect(positiveIntegerValue("30")).toBe(30);
    expect(positiveIntegerValue("0")).toBeNull();
    expect(positiveIntegerValue("3.5")).toBeNull();
    expect(decimalValue("6.00")).toBe("6.00");
    expect(decimalValue("-1")).toBeNull();
    expect(optionalTextValue("  ")).toBeNull();
    expect(optionalTextValue(" Dr. ")).toBe("Dr.");
  });
});
