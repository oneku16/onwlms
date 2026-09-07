"use client";

import type { FormEvent } from "react";
import { useState } from "react";

import { clientApiRequest } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { useCsrfProtection } from "@/lib/api/use-csrf";
import type { ResourceSummary } from "@/lib/api/resources";

const supportedOverrideFeatures = new Set(["mcp", "timetable_generation"]);

function asIso(value: FormDataEntryValue | null): string | null {
  const input = String(value ?? "").trim();
  return input ? new Date(input).toISOString() : null;
}

function successfulMutation(value: unknown): true {
  if (typeof value !== "object" || value === null) {
    throw new Error("The platform policy response is not supported.");
  }
  return true;
}

function MutationState({ message }: { readonly message: string | null }) {
  return message ? (
    <p className="inline-notice" role="status">
      {message}
    </p>
  ) : null;
}

export function SubscriptionAssignmentForm({
  organizations,
  plans,
}: {
  readonly organizations: readonly ResourceSummary[];
  readonly plans: readonly ResourceSummary[];
}) {
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const csrfAvailable = useCsrfProtection();

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setMessage(null);
    setError(null);
    setSubmitting(true);
    const form = new FormData(event.currentTarget);
    const organizationId = String(form.get("organizationId") ?? "").trim();
    try {
      await clientApiRequest(
        `/api/v1/platform/organizations/${encodeURIComponent(organizationId)}/subscription`,
        successfulMutation,
        {
          method: "PUT",
          body: {
            plan_id: String(form.get("planId") ?? "").trim(),
            status: String(form.get("status") ?? "active"),
            starts_at: asIso(form.get("startsAt")),
            ends_at: asIso(form.get("endsAt")),
          },
        },
      );
      setMessage(
        `Subscription policy updated for organization ${organizationId}.`,
      );
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The subscription policy could not be updated.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="form-card" onSubmit={(event) => void submit(event)}>
      <div className="form-grid">
        <label>
          Organization
          <select name="organizationId" required defaultValue="">
            <option value="" disabled>
              Select an organization
            </option>
            {organizations.map((organization) => (
              <option key={organization.id} value={organization.id}>
                {organization.title}
              </option>
            ))}
          </select>
        </label>
        <label>
          Plan
          <select name="planId" required defaultValue="">
            <option value="" disabled>
              Select a plan
            </option>
            {plans.map((plan) => (
              <option key={plan.id} value={plan.id}>
                {plan.title}
              </option>
            ))}
          </select>
        </label>
        <label>
          Status
          <select name="status" defaultValue="active">
            <option value="trialing">Trialing</option>
            <option value="active">Active</option>
          </select>
        </label>
        <label>
          Starts at
          <input name="startsAt" type="datetime-local" required />
        </label>
        <label>
          Ends at (optional)
          <input name="endsAt" type="datetime-local" />
        </label>
      </div>
      <MutationState message={message} />
      {error ? (
        <p className="inline-alert" role="alert">
          {error}
        </p>
      ) : null}
      <div className="form-actions">
        <button
          className="button"
          type="submit"
          disabled={
            !csrfAvailable ||
            submitting ||
            organizations.length === 0 ||
            plans.length === 0
          }
        >
          {submitting ? "Saving…" : "Assign subscription"}
        </button>
      </div>
    </form>
  );
}

export function EntitlementOverrideForm({
  organizations,
  features,
}: {
  readonly organizations: readonly ResourceSummary[];
  readonly features: readonly ResourceSummary[];
}) {
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const csrfAvailable = useCsrfProtection();
  const supportedFeatures = features.filter(
    (feature) =>
      feature.code !== undefined && supportedOverrideFeatures.has(feature.code),
  );

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setMessage(null);
    setError(null);
    setSubmitting(true);
    const form = new FormData(event.currentTarget);
    const organizationId = String(form.get("organizationId") ?? "").trim();
    const enabled = form.get("enabled") === "on";
    const usageAmount = String(form.get("usageAmount") ?? "").trim();
    try {
      await clientApiRequest(
        `/api/v1/platform/organizations/${encodeURIComponent(organizationId)}/entitlements`,
        successfulMutation,
        {
          method: "PUT",
          body: {
            feature: String(form.get("feature") ?? ""),
            enabled,
            usage_limit:
              enabled && usageAmount
                ? {
                    amount: Number(usageAmount),
                    period: String(form.get("usagePeriod") ?? "absolute"),
                  }
                : null,
            expires_at: asIso(form.get("expiresAt")),
          },
        },
      );
      setMessage(
        `Feature override updated for organization ${organizationId}.`,
      );
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The feature override could not be updated.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="form-card" onSubmit={(event) => void submit(event)}>
      <div className="form-grid">
        <label>
          Organization
          <select name="organizationId" required defaultValue="">
            <option value="" disabled>
              Select an organization
            </option>
            {organizations.map((organization) => (
              <option key={organization.id} value={organization.id}>
                {organization.title}
              </option>
            ))}
          </select>
        </label>
        <label>
          Feature
          <select name="feature" required defaultValue="">
            <option value="" disabled>
              Select a supported feature
            </option>
            {supportedFeatures.map((feature) => (
              <option key={feature.id} value={feature.code}>
                {feature.title}
              </option>
            ))}
          </select>
        </label>
        <label className="checkbox-label">
          <input name="enabled" type="checkbox" defaultChecked />
          Enabled
        </label>
        <label>
          Usage amount (optional)
          <input name="usageAmount" type="number" min="1" step="1" />
        </label>
        <label>
          Usage period
          <select name="usagePeriod" defaultValue="absolute">
            <option value="month">Month</option>
            <option value="academic_term">Academic term</option>
            <option value="absolute">Absolute</option>
          </select>
        </label>
        <label>
          Expires at (optional)
          <input name="expiresAt" type="datetime-local" />
        </label>
      </div>
      <MutationState message={message} />
      {error ? (
        <p className="inline-alert" role="alert">
          {error}
        </p>
      ) : null}
      <div className="form-actions">
        <button
          className="button"
          type="submit"
          disabled={
            !csrfAvailable ||
            submitting ||
            organizations.length === 0 ||
            supportedFeatures.length === 0
          }
        >
          {submitting ? "Saving…" : "Set feature override"}
        </button>
      </div>
    </form>
  );
}
