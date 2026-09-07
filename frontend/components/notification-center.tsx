"use client";

import { useState } from "react";

import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  notificationChannels,
  parseNotification,
  parseNotificationPreference,
  type NotificationChannel,
  type NotificationItem,
  type NotificationPreference,
} from "@/lib/api/notifications";
import { useCsrfProtection } from "@/lib/api/use-csrf";

const channelLabels: Readonly<Record<NotificationChannel, string>> = {
  in_app: "In-app",
  email: "Email",
  sms: "SMS",
  whatsapp: "WhatsApp",
  telegram: "Telegram",
};

export function NotificationCenter({
  canManagePreferences,
  canRetry,
  initialNotifications,
  initialPreferences,
  organizationId,
}: {
  readonly canManagePreferences: boolean;
  readonly canRetry: boolean;
  readonly initialNotifications: readonly NotificationItem[];
  readonly initialPreferences: readonly NotificationPreference[];
  readonly organizationId: string;
}) {
  const [notifications, setNotifications] = useState(initialNotifications);
  const [preferences, setPreferences] = useState(initialPreferences);
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();

  async function setPreference(
    channel: NotificationChannel,
    enabled: boolean,
  ): Promise<void> {
    const key = `preference-${channel}`;
    setPendingKey(key);
    setMessage(null);
    setError(null);
    try {
      const updated = await clientApiRequest(
        `/api/v1/notifications/preferences/${channel}`,
        parseNotificationPreference,
        {
          method: "PUT",
          organizationId,
          body: { enabled },
        },
      );
      setPreferences((current) =>
        current.map((preference) =>
          preference.channel === channel ? updated : preference,
        ),
      );
      setMessage(`${channelLabels[channel]} preference saved.`);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The notification preference could not be saved.",
      );
    } finally {
      setPendingKey(null);
    }
  }

  async function mutateNotification(
    notification: NotificationItem,
    action: "read" | "retry",
  ): Promise<void> {
    const key = `${action}-${notification.id}`;
    setPendingKey(key);
    setMessage(null);
    setError(null);
    try {
      const updated = await clientApiRequest(
        `/api/v1/notifications/${encodeURIComponent(notification.id)}/${action}`,
        parseNotification,
        { method: "POST", organizationId },
      );
      setNotifications((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
      setMessage(
        action === "read"
          ? `“${updated.subject}” marked as read.`
          : `Delivery retried for “${updated.subject}”.`,
      );
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : action === "read"
            ? "The notification could not be marked as read."
            : "The notification delivery could not be retried.",
      );
    } finally {
      setPendingKey(null);
    }
  }

  return (
    <div className="notification-layout">
      <section className="form-card" aria-labelledby="notification-preferences">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Delivery controls</p>
            <h2 id="notification-preferences">Notification preferences</h2>
          </div>
        </div>
        <div className="preference-grid">
          {notificationChannels.map((channel) => {
            const preference = preferences.find(
              (candidate) => candidate.channel === channel,
            );
            const key = `preference-${channel}`;
            return (
              <label className="preference-control" key={channel}>
                <span>
                  <strong>{channelLabels[channel]}</strong>
                  <small>
                    {channel === "in_app"
                      ? "Messages shown securely inside OwnSIS."
                      : "Requires a configured organization delivery adapter."}
                  </small>
                </span>
                <input
                  type="checkbox"
                  checked={preference?.enabled ?? false}
                  disabled={
                    !canManagePreferences ||
                    !csrfAvailable ||
                    pendingKey !== null
                  }
                  onChange={(event) =>
                    void setPreference(channel, event.currentTarget.checked)
                  }
                  aria-label={`${channelLabels[channel]} notifications`}
                  aria-busy={pendingKey === key}
                />
              </label>
            );
          })}
        </div>
        {!canManagePreferences ? (
          <p className="inline-notice">
            Your current membership cannot change notification preferences.
          </p>
        ) : !csrfAvailable ? (
          <p className="inline-notice">
            Preference editing is unavailable because the session has no CSRF
            token.
          </p>
        ) : null}
      </section>

      {error ? (
        <p className="inline-alert" role="alert">
          {error}
        </p>
      ) : null}
      {message ? (
        <p className="inline-success" role="status">
          {message}
        </p>
      ) : null}

      <section aria-labelledby="notification-messages">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Recipient-scoped inbox</p>
            <h2 id="notification-messages">Messages</h2>
          </div>
          <span className="status-pill">
            {notifications.length.toLocaleString()} total
          </span>
        </div>
        {notifications.length === 0 ? (
          <div className="state-panel">
            <p className="state-kicker">Inbox clear</p>
            <h2>No notifications yet</h2>
            <p>New messages addressed to your active membership appear here.</p>
          </div>
        ) : (
          <div className="notification-list">
            {notifications.map((notification) => {
              const unread = notification.readAt === null;
              return (
                <article
                  className={`notification-card${unread ? " notification-unread" : ""}`}
                  key={notification.id}
                >
                  <div className="resource-card-heading">
                    <div>
                      <p className="eyebrow">
                        {channelLabels[notification.channel]}
                      </p>
                      <h2>{notification.subject}</h2>
                    </div>
                    <span className="status-pill">{notification.status}</span>
                  </div>
                  <p>{notification.body}</p>
                  <time dateTime={notification.createdAt}>
                    {new Intl.DateTimeFormat(undefined, {
                      dateStyle: "medium",
                      timeStyle: "short",
                    }).format(new Date(notification.createdAt))}
                  </time>
                  <div className="button-row">
                    {unread ? (
                      <button
                        className="button button-secondary button-small"
                        type="button"
                        disabled={!csrfAvailable || pendingKey !== null}
                        onClick={() =>
                          void mutateNotification(notification, "read")
                        }
                      >
                        {pendingKey === `read-${notification.id}`
                          ? "Saving…"
                          : "Mark as read"}
                      </button>
                    ) : null}
                    {notification.channel !== "in_app" &&
                    notification.status === "retry" ? (
                      <button
                        className="button button-small"
                        type="button"
                        disabled={
                          !canRetry || !csrfAvailable || pendingKey !== null
                        }
                        onClick={() =>
                          void mutateNotification(notification, "retry")
                        }
                      >
                        {pendingKey === `retry-${notification.id}`
                          ? "Retrying…"
                          : "Retry delivery"}
                      </button>
                    ) : null}
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
