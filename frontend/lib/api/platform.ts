import {
  asBoolean,
  asNumber,
  asRecord,
  asString,
  unwrapPayload,
  type UnknownRecord,
} from "@/lib/api/validation";

export const featureCodes = [
  "academic",
  "moodle_integration",
  "ownid_sso",
  "mcp",
  "hr",
  "finance",
  "library",
  "dormitory",
  "advanced_analytics",
  "multiple_administrators",
  "custom_roles",
  "timetable_generation",
  "white_label",
] as const;

export type FeatureCode = (typeof featureCodes)[number];

export const usagePeriods = ["month", "academic_term", "absolute"] as const;

export type UsagePeriod = (typeof usagePeriods)[number];

export interface UsageLimitView {
  readonly amount: number;
  readonly period: UsagePeriod;
}

export interface PlanGrantView {
  readonly feature: FeatureCode;
  readonly usageLimit: UsageLimitView | null;
}

export interface PlanView {
  readonly id: string;
  readonly code: string;
  readonly displayName: string;
  readonly active: boolean;
  readonly grants: readonly PlanGrantView[];
}

export interface FeatureView {
  readonly id: string;
  readonly code: FeatureCode;
  readonly displayName: string;
  readonly baseIncluded: boolean;
}

export function isFeatureCode(value: string): value is FeatureCode {
  return featureCodes.some((code) => code === value);
}

function isUsagePeriod(value: string): value is UsagePeriod {
  return usagePeriods.some((period) => period === value);
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

function parseUsageLimit(value: unknown): UsageLimitView | null {
  if (value === null || value === undefined) {
    return null;
  }
  const contract = "usage limit";
  const record = requireRecord(value, contract);
  const amount = asNumber(record.amount);
  const period = requireString(record, "period", contract);
  if (
    amount === undefined ||
    !Number.isInteger(amount) ||
    !isUsagePeriod(period)
  ) {
    throw new Error(`The ${contract} response is not supported.`);
  }
  return { amount, period };
}

function parsePlanGrant(value: unknown): PlanGrantView {
  const contract = "plan grant";
  const record = requireRecord(value, contract);
  const feature = requireString(record, "feature", contract);
  if (!isFeatureCode(feature)) {
    throw new Error(`The ${contract} response is not supported.`);
  }
  return { feature, usageLimit: parseUsageLimit(record.usage_limit) };
}

export function parsePlan(value: unknown): PlanView {
  const contract = "plan";
  const record = requireRecord(value, contract);
  if (!Array.isArray(record.grants)) {
    throw new Error(`The ${contract} response is not supported.`);
  }
  return {
    id: requireString(record, "id", contract),
    code: requireString(record, "code", contract),
    displayName: requireString(record, "display_name", contract),
    active: requireBoolean(record, "active", contract),
    grants: record.grants.map(parsePlanGrant),
  };
}

export function parsePlans(value: unknown): readonly PlanView[] {
  const payload = unwrapPayload(value);
  if (!Array.isArray(payload)) {
    throw new Error("The plan list response is not supported.");
  }
  return payload.map(parsePlan);
}

export function parseFeature(value: unknown): FeatureView {
  const contract = "feature";
  const record = requireRecord(value, contract);
  const code = requireString(record, "code", contract);
  if (!isFeatureCode(code)) {
    throw new Error(`The ${contract} response is not supported.`);
  }
  return {
    id: requireString(record, "id", contract),
    code,
    displayName: requireString(record, "display_name", contract),
    baseIncluded: requireBoolean(record, "base_included", contract),
  };
}

export function parseFeatures(value: unknown): readonly FeatureView[] {
  const payload = unwrapPayload(value);
  if (!Array.isArray(payload)) {
    throw new Error("The feature list response is not supported.");
  }
  return payload.map(parseFeature);
}

export const subscriptionStatuses = [
  "trialing",
  "active",
  "suspended",
  "canceled",
] as const;

export type SubscriptionStatus = (typeof subscriptionStatuses)[number];

export interface SubscriptionView {
  readonly id: string;
  readonly organizationId: string;
  readonly planId: string;
  readonly status: SubscriptionStatus;
  readonly startsAt: string;
  readonly endsAt: string | null;
}

function isSubscriptionStatus(value: string): value is SubscriptionStatus {
  return subscriptionStatuses.some((status) => status === value);
}

/** Parse one organization's current subscription and its lifecycle state. */
export function parseSubscription(value: unknown): SubscriptionView {
  const record = asRecord(unwrapPayload(value));
  const id = asString(record?.id);
  const organizationId = asString(record?.organization_id);
  const planId = asString(record?.plan_id);
  const status = asString(record?.status);
  const startsAt = asString(record?.starts_at);
  const endsAt = record?.ends_at === null ? null : asString(record?.ends_at);
  if (
    !record ||
    !id ||
    !organizationId ||
    !planId ||
    !status ||
    !isSubscriptionStatus(status) ||
    !startsAt ||
    endsAt === undefined
  ) {
    throw new Error("The subscription response is not supported.");
  }
  return { id, organizationId, planId, status, startsAt, endsAt };
}
