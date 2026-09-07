import {
  asBoolean,
  asRecord,
  asString,
  unwrapPayload,
} from "@/lib/api/validation";

export const notificationChannels = [
  "in_app",
  "email",
  "sms",
  "whatsapp",
  "telegram",
] as const;

export type NotificationChannel = (typeof notificationChannels)[number];
export type NotificationStatus =
  "pending" | "sent" | "retry" | "failed" | "read";

export interface NotificationItem {
  readonly id: string;
  readonly channel: NotificationChannel;
  readonly subject: string;
  readonly body: string;
  readonly status: NotificationStatus;
  readonly createdAt: string;
  readonly readAt: string | null;
}

export interface NotificationPreference {
  readonly channel: NotificationChannel;
  readonly enabled: boolean;
}

function isChannel(value: string): value is NotificationChannel {
  return notificationChannels.some((channel) => channel === value);
}

function isStatus(value: string): value is NotificationStatus {
  return ["pending", "sent", "retry", "failed", "read"].some(
    (status) => status === value,
  );
}

export function parseNotification(value: unknown): NotificationItem {
  const record = asRecord(unwrapPayload(value));
  const id = asString(record?.id);
  const channel = asString(record?.channel);
  const subject = asString(record?.subject);
  const body = asString(record?.body);
  const status = asString(record?.status);
  const createdAt = asString(record?.created_at);
  const readAtValue = record?.read_at;
  if (
    !id ||
    !channel ||
    !isChannel(channel) ||
    !subject ||
    !body ||
    !status ||
    !isStatus(status) ||
    !createdAt ||
    (readAtValue !== null && asString(readAtValue) === undefined)
  ) {
    throw new Error("The notification response is not supported.");
  }
  return {
    id,
    channel,
    subject,
    body,
    status,
    createdAt,
    readAt: readAtValue === null ? null : (asString(readAtValue) ?? null),
  };
}

export function parseNotifications(
  value: unknown,
): readonly NotificationItem[] {
  const payload = unwrapPayload(value);
  if (!Array.isArray(payload)) {
    throw new Error("The notification list response is not supported.");
  }
  return payload.map(parseNotification);
}

export function parseNotificationPreference(
  value: unknown,
): NotificationPreference {
  const record = asRecord(unwrapPayload(value));
  const channel = asString(record?.channel);
  const enabled = asBoolean(record?.enabled);
  if (!channel || !isChannel(channel) || enabled === undefined) {
    throw new Error("The notification preference response is not supported.");
  }
  return { channel, enabled };
}

export function parseNotificationPreferences(
  value: unknown,
): readonly NotificationPreference[] {
  const payload = unwrapPayload(value);
  if (!Array.isArray(payload)) {
    throw new Error("The notification preferences response is not supported.");
  }
  return payload.map(parseNotificationPreference);
}
