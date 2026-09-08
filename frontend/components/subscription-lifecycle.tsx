"use client";

import type { ChangeEvent } from "react";
import { useState } from "react";

import { ResourceOptions } from "@/components/resource-options";
import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { parseSubscription, type SubscriptionView } from "@/lib/api/platform";
import { resourceTitle, type ResourceSummary } from "@/lib/api/resources";
import { useCsrfProtection } from "@/lib/api/use-csrf";

type LifecycleAction = "suspend" | "reactivate" | "cancel";

function formatInstant(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf())
    ? value
    : new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(parsed);
}

/** Suspend, reactivate, or cancel one organization's current subscription. */
export function SubscriptionLifecycle({
  organizations,
  plans,
}: {
  readonly organizations: readonly ResourceSummary[];
  readonly plans: readonly ResourceSummary[];
}) {
  const [organizationId, setOrganizationId] = useState("");
  const [subscription, setSubscription] = useState<SubscriptionView | null>(
    null,
  );
  const [loading, setLoading] = useState(false);
  const [pendingAction, setPendingAction] = useState<LifecycleAction | null>(
    null,
  );
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const csrfAvailable = useCsrfProtection();

  async function loadSubscription(value: string): Promise<void> {
    setOrganizationId(value);
    setSubscription(null);
    setMessage(null);
    setError(null);
    setNotice(null);
    if (!value) {
      return;
    }
    setLoading(true);
    try {
      setSubscription(
        await clientApiRequest(
          `/api/v1/platform/organizations/${encodeURIComponent(value)}/subscription`,
          parseSubscription,
        ),
      );
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 404) {
        setNotice("This organization has no subscription to manage yet.");
      } else {
        setError(
          caught instanceof ApiError
            ? caught.message
            : "The current subscription could not be loaded.",
        );
      }
    } finally {
      setLoading(false);
    }
  }

  async function transition(action: LifecycleAction): Promise<void> {
    setMessage(null);
    setError(null);
    setPendingAction(action);
    try {
      const updated = await clientApiRequest(
        `/api/v1/platform/organizations/${encodeURIComponent(organizationId)}/subscription/${action}`,
        parseSubscription,
        { method: "POST" },
      );
      setSubscription(updated);
      setMessage(`The subscription is now ${updated.status}.`);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The subscription lifecycle could not be changed.",
      );
    } finally {
      setPendingAction(null);
    }
  }

  const canSuspend =
    subscription?.status === "active" || subscription?.status === "trialing";
  const canReactivate = subscription?.status === "suspended";
  const canCancel = subscription !== null && subscription.status !== "canceled";

  return (
    <section className="form-card" aria-labelledby="subscription-lifecycle">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Commercial lifecycle</p>
          <h2 id="subscription-lifecycle">Subscription state</h2>
        </div>
        {subscription ? (
          <span className="status-pill">{subscription.status}</span>
        ) : null}
      </div>
      <p className="inline-notice">
        Suspending or canceling withdraws the plan&apos;s feature entitlements.
        It does not change any person&apos;s permissions.
      </p>
      <div className="form-grid">
        <label>
          Organization
          <select
            name="organizationId"
            value={organizationId}
            onChange={(event: ChangeEvent<HTMLSelectElement>) =>
              void loadSubscription(event.target.value)
            }
          >
            <ResourceOptions
              placeholder="Select an organization"
              resources={organizations}
            />
          </select>
        </label>
      </div>
      {loading ? <p className="inline-notice">Loading subscription…</p> : null}
      {notice ? <p className="inline-notice">{notice}</p> : null}
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
      {subscription ? (
        <dl className="resource-metadata">
          <div>
            <dt>Plan</dt>
            <dd>{resourceTitle(plans, subscription.planId, "Plan")}</dd>
          </div>
          <div>
            <dt>Starts</dt>
            <dd>{formatInstant(subscription.startsAt)}</dd>
          </div>
          <div>
            <dt>Ends</dt>
            <dd>
              {subscription.endsAt
                ? formatInstant(subscription.endsAt)
                : "No end date"}
            </dd>
          </div>
        </dl>
      ) : null}
      {!csrfAvailable ? (
        <p className="inline-notice">
          Lifecycle changes are unavailable because the session has no CSRF
          token.
        </p>
      ) : null}
      <div className="button-row">
        <button
          className="button button-secondary"
          type="button"
          disabled={!canSuspend || !csrfAvailable || pendingAction !== null}
          onClick={() => void transition("suspend")}
        >
          {pendingAction === "suspend" ? "Suspending…" : "Suspend"}
        </button>
        <button
          className="button button-secondary"
          type="button"
          disabled={!canReactivate || !csrfAvailable || pendingAction !== null}
          onClick={() => void transition("reactivate")}
        >
          {pendingAction === "reactivate" ? "Reactivating…" : "Reactivate"}
        </button>
        <button
          className="button"
          type="button"
          disabled={!canCancel || !csrfAvailable || pendingAction !== null}
          onClick={() => void transition("cancel")}
        >
          {pendingAction === "cancel" ? "Canceling…" : "Cancel subscription"}
        </button>
      </div>
    </section>
  );
}
